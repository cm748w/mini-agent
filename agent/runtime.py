import os
import json
import config
from config import logger, client
from tools import registry
from datetime import datetime
from agent import Session, SessionManager, needs_compaction, compact, Trace, manager
from .prompts import SYSTEM_PROMPT

MODEL_NAME = config.MODEL_NAME
MAX_ROUNDS = config.MAX_ROUNDS

def agent_run(user_query: str, session: Session, repo: SessionManager = manager): # 接受会话
    trace = Trace()
    # 使用该会话的消息列表
    messages = session.messages

    # system 固定在头部、且只放一次; 
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    # 在消息列表中加入 "用户的提问"
    messages.append({"role": "user", "content": user_query})

    # 如果需要"上下文压缩", 则进行上下文压缩
    if needs_compaction(messages, config.MAX_MESSAGES):
        session.messages = compact(messages, config.KEEP_RECENT)
        messages = session.messages
        logger.info(f"上下文已压缩: {len(messages)}条消息")
    
    trace.add(0, "user", content=user_query)
    logger.debug(f"[用户问题]\n{user_query}")

    try:
        # 进行轮次循环
        for round_idx in range(1, MAX_ROUNDS+1):
            try:
                # 发送 API 请求
                response = client.chat.completions.create(
                    model=MODEL_NAME, messages=messages,
                    tools=registry.schemas(), tool_choice="auto",
                )
            except Exception as e:
                logger.exception(f"API 调用失败: {type(e).__name__}: {e}")
                trace.add(round_idx, "error", error=str(e))
                return f"抱歉,模型调用失败: {type(e).__name__}"

            # 将 "模型返回" 转为 "字典"
            resp_dict = response.model_dump()

            # 日志打印完整的 "模型返回内容"
            logger.debug(f"[{MODEL_NAME}]\n{json.dumps(resp_dict, ensure_ascii=False, indent=2)}")

            # 从字典 resp_dict 中提取模型思考过程(不同模型有不同写法)
            reasoning = resp_dict["choices"][0]["message"].get("reasoning_content")
            if reasoning:
                logger.info(f"[思考过程]\n {reasoning}")
                trace.add(round_idx, "thought", text=reasoning)
            # 提取响应中完整的 message, 并将其转为字典存入 "消息列表"
            message = response.choices[0].message
            messages.append(message.model_dump())

            # 判断是否需要调用工具
            if not message.tool_calls:
                trace.add(round_idx, "final", content=message.content)
                logger.info(f"[最终结果]\n{message.content}")
                return message.content # 结束循环

            # 调用工具的同时,防止遗漏模型返回的信息
            if message.content:
                trace.add(round_idx, "assistant_content", content=message.content)

            # 遍历模型要调用的工具
            for tool_call in message.tool_calls:
                # 获取工具名称
                func_name = tool_call.function.name
                try:
                    # 解析参数 —— 把 json 解析为字典
                    func_args = json.loads(tool_call.function.arguments)
                except (json.JSONDecodeError, TypeError) as e:
                    func_args = {}
                    raw_args = str(tool_call.function.arguments)
                    logger.warning(
                        "[工具参数解析失败] round=%s id=%s raw=%s error=%s",
                        round_idx, tool_call.id, func_name,
                        raw_args[:200], e
                    )
                    trace.add(
                        round_idx, "tool_call_error",
                        id=tool_call.id,
                        name=func_name,
                        raw_args=raw_args[:200],
                        error=f"{type(e).__name__}: {e}"
                    )
                    result = f"参数解析失败: {e}, 请重新给出合法的 JSON 参数"
                else:
                    trace.add(
                        round_idx, "tool_call", id=tool_call.id,
                        name=func_name, args=func_args
                    )
                    # 判断模型要调用的 tool 是否在 "注册表" 里
                    if func_name in registry:
                        logger.info(
                            "[调用工具] round=%s id=%s name=%s",
                            round_idx, tool_call.id, func_name
                        )
                        try:
                            # 存储工具执行结果
                            result = registry.execute(func_name, **func_args)
                        except Exception as e:
                            logger.exception(
                                "[工具执行失败] round=%s id=%s name=%s, args=%s",
                                round_idx, tool_call.id, func_name, func_args
                            )
                            trace.add(
                                round_idx, "tool_error",id=tool_call.id,
                                name=func_name,error=f"{type(e).__name__}: {e}"
                            )
                            # 存储错误信息
                            result = f"工具执行错误: {type(e).__name__}: {e},请检查参数后重试"
                    else:
                        logger.warning(
                            "[未知工具] round=%s id=%s name=%s",
                            round_idx, tool_call.id, func_name
                        )
                        trace.add(
                            round_idx, "tool_error", id=tool_call.id,
                            name=func_name, error="unknown tool"
                        )
                        # 存储 "未发现工具" 信息
                        result = f"没有发现{func_name}这个工具, 请检查工具名称"

                # 所有分支统一记录 tool_result
                result_str = str(result) # 执行结果可能不是字符串
                trace.add(
                    round_idx, "tool_result", name=func_name,
                    id=tool_call.id, result_len=len(result_str),
                    result=result_str[:200] + ("..." if len(result_str) > 200 else "")
                )
                # 执行结果放进messages
                messages.append({
                    "role": "tool", "content": str(result),
                    "tool_call_id": tool_call.id, "name": func_name
                })
        else:
            logger.info(f"已达到最大轮次限制{MAX_ROUNDS},强制结束")
            trace.add(
                # +1作为收尾标记
                MAX_ROUNDS+1, "max_rounds",
                content="已达到最大轮次限制,工具调用轮次过多"
            )
            return "已达到最大轮次限制,工具调用轮次过多,请缩小任务后重试。"
    except Exception as e:
        logger.exception("agent_run 未处理异常")
        trace.add(
            locals().get("round_idx", 0),
            "fatal",
            error=f"{type(e).__name__}: {e}"
        )
        return f"Agent内部错误: {type(e).__name__}"
    finally:
        # 更新会话时间
        session.touch()

        # 把会话保存到 `data/sessions.json`
        repo.save_all(config.SESSIONS_FILE)

        # 即使 try 里 return,finally 也一定会执行
        try:
            os.makedirs("logs", exist_ok=True)
            filename = f"logs/trace_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            # 把 trace 文件保存到 `logs/` 文件夹下
            trace.save(filename)
            logger.info(f"Trace已保存: {filename}")
        except Exception:
            logger.exception("Trace 保存失败")
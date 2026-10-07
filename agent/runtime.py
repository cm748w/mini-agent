import os
import json
import config
from config import logger, client
from tools import registry
from datetime import datetime
from agent import (
    Session, SessionManager, needs_compaction, compact, build_context, 
    over_token_limit, trim_recent_by_tokens, trim_recent_by_count, 
    history_tokens, Trace, manager, cap_tool_result, archive_messages
)
from .summarizer import summarize
from .prompts import SYSTEM_PROMPT
from .state_updater import update_state, classify_turn
from .state import new_task_state

def agent_run(user_query: str, session: Session, repo: SessionManager = manager): # 接受会话
    # 初始化【追踪器】
    trace = Trace()
    # 初始化【消息列表】
    messages = session.messages

    """
    # state  —— 状态
    # status —— 进展(是state的一个键, 表示goal的进展: in_progress 或 done 或 blocked)
    """

    # 追加【用户消息】前, 做判断
    # 如果 state["status"] 为 "已完成" 或 "阻塞" :
    #   则重置 state["status"] 为 "进行时" 
    # 如果【用户消息】与 state["goal"] 无关:
    #   则重置整个会话(new_goal) , 并清空【消息列表】
    if session.state.get("status") in ("done", "blocked"):

        # verdict —— 裁决
        # 调用LLM判断, 并接受【判断结果】
        verdict = classify_turn(session.state, messages, user_query)

        # 如果【用户消息】和 state["goal"] 没关系, 
        # 则重置 state (仅保留新的 goal), 并清空当前的【消息列表】messages
        if verdict["relation"] == "new_task":
            session.state = new_task_state(verdict["new_goal"] or user_query)
            messages.clear() # clear() —— 清空list的所有元素
            
            logger.info("检测到新任务, State 已轮转, Recent 已清空")
        else:
            # 仅重置 status
            session.state["status"] = "in_progress"

    # 如果是第一次交流, 将【用户信息】设为目标(state["goal"])
    if not session.state.get("goal"):
        session.state["goal"] = user_query

    # 将【用户消息】追加到【消息列表】
    messages.append({"role": "user", "content": user_query})

    # 初始化【裁剪列表】—— 取自 "消息列表"
    dropped = []

    # 按【token数】裁剪
    if over_token_limit(messages, config.RECENT_TOKEN_LIMIT):

        # 把 messages 一分为二, 左边是【保留部分】, 右边是【裁剪部分】
        messages, dropped = trim_recent_by_tokens(messages, config.KEEP_RECENT_TOKENS)

        # 把【保留部分】同步给 session.messages
        session.messages = messages

        logger.info(
            f"消息列表【token数】超标, 已裁剪: 保留 {len(messages)} 条消息/"
            f"\n{history_tokens(messages)} token; \n{len(dropped)} 条旧消息待摘要"
        )
    # 按【消息数】裁剪
    elif needs_compaction(messages, config.MAX_MESSAGES):

        # 把 messages 一分为二, 左边是【保留部分】, 右边是【裁剪部分】
        messages, dropped = trim_recent_by_count(messages, config.KEEP_RECENT)

        # 把【保留部分】同步给 session.messages
        session.messages = messages
        logger.info(
            f"消息列表【条数】超标, 已裁剪: \n保留 {len(messages)} 条消息"
            f" \n{len(dropped)} 条旧消息待摘要"
        )

    """
      archive 归档
     【旧摘要】+【裁剪列表】+【归档指针】->【新摘要】
      如果归档失败, 则保持摘要不变
    """

    # 如果【裁剪列表】里有东西, 则做一次【归档】+【总结】
    if dropped:
        archive_path = archive_messages(session.id, dropped)
        logger.info(f"已归档 {len(dropped)} 条原始消息: {archive_path}")
        # 如果【总结】失败, 则会沿用【旧总结】
        session.summary = summarize(session.summary, dropped, archive_path)

    trace.add(0, "user", content=user_query)
    logger.debug(f"[用户问题]\n{user_query}")

    try:
        # 进行轮次循环
        for round_idx in range(1, config.MAX_ROUNDS+1):
            try:
                # 构建【上下文】
                context = build_context(SYSTEM_PROMPT, session.state, session.summary, messages)
                # 发送 API 请求
                response = client.chat.completions.create(
                    model=config.MODEL_NAME, messages=context,
                    tools=registry.schemas(), tool_choice="auto",
                )
            except Exception as e:
                logger.exception(f"API 调用失败: {type(e).__name__}: {e}")
                trace.add(round_idx, "error", error=str(e))
                return f"抱歉,模型调用失败: {type(e).__name__}"

            # 将 "模型返回" 转为 "字典"
            resp_dict = response.model_dump()

            # 日志打印完整的 "模型返回内容"
            logger.debug(f"[{config.MODEL_NAME}]\n{json.dumps(resp_dict, ensure_ascii=False, indent=2)}")

            # 从字典 resp_dict 中提取模型思考过程(不同模型有不同写法)
            reasoning = resp_dict["choices"][0]["message"].get("reasoning_content")
            if reasoning:
                logger.info(f"[思考过程]\n {reasoning}")
                trace.add(round_idx, "thought", text=reasoning)
            # 提取响应中完整的 message, 并将其转为字典存入 "消息列表"
            message = response.choices[0].message

            # 记录本轮新消息的起点: 之后 append 的 assistant/tool 消息都算"本轮消息"
            mark = len(messages)
            messages.append(message.model_dump())

            # 判断是否要调用工具
            if not message.tool_calls:
                # 让 LLM 更新 state(仅包括: progerss、key_facts、goal、next_step)
                session.state = update_state(session.state, messages[mark:])

                # 手动设置 state["status"] 为 done
                session.state["status"] = "done"
                # 手动设置 state["next_step"] 为空
                session.state["next_step"] = ""

                trace.add(round_idx, "final", content=message.content)
                logger.info(f"[最终结果]\n{message.content}")
                return message.content # 结束循环

            # 调用工具的同时,防止遗漏 LLM 返回的信息
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
                    # 获取 LLM 返回的【原始参数】
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
                    # 判断 LLM 要调用的【工具】是否在【注册表】里
                    if func_name in registry:
                        logger.info(
                            "[调用工具] round=%s id=%s name=%s",
                            round_idx, tool_call.id, func_name
                        )
                        try:
                            # 保存【工具】的【执行结果】
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
                            # 保存【错误信息】
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
                        # 保存【异常信息】
                        result = f"没有发现{func_name}这个工具, 请检查工具名称"

                # 把【结果】转成【字符串格式】
                result_str = str(result)

                # cap —— 限制

                # "read_file工具" 是 "受控下钻通道",自带【限量参数】(max_chars)
                if func_name == "read_file":
                    # 保护【read_file工具】的【执行结果】
                    capped = result_str
                else:
                    # 处理 result_str , 保证其不超标
                    capped = cap_tool_result(
                        result_str, func_name, config.TOOL_RESULT_TOKEN_LIMIT
                    )

                trace.add(
                    round_idx, "tool_result", name=func_name,
                    id=tool_call.id, result_len=len(capped),
                    result=capped[:200] + ("..." if len(capped) > 200 else "")
                )

                messages.append({
                    "role": "tool", "content": capped,
                    "tool_call_id": tool_call.id, "name": func_name
                })

            # 让 LLM 更新 state(仅包括: progerss、key_facts、goal、next_step)
            session.state = update_state(session.state, messages[mark:])
        else:
            logger.info(f"已达到最大轮次限制{config.MAX_ROUNDS},强制结束")
            session.state["status"] = "blocked"
            trace.add(
                # +1作为收尾标记
                config.MAX_ROUNDS+1, "max_rounds",
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
        # 更新 session["updated_at"]
        session.touch()

        # 把会话保存到 `data/sessions.json`
        repo.save_all(config.SESSIONS_FILE)

        # 即使 在try里return, finally也一定会执行
        try:
            # 创建【日志文件夹】
            os.makedirs("logs", exist_ok=True)
            # 构建【日志名称】
            filename = f"logs/trace_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            # 保存【追踪文件】(trace) 到 `logs/` 文件夹下
            trace.save(filename)

            logger.info(f"Trace已保存: {filename}")
        except Exception:
            logger.exception("Trace 保存失败")

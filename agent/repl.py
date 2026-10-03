from agent.session import Session, manager
from agent.runtime import agent_run

"""
REPL —— 交互式编程环境
Read-Eval-Print Loop 读取-求值-打印 循环
"""

def open_session(session: Session) -> bool:
    """窗口内对话。返回 True = 回菜单; False = 退出整个程序"""
    print(f"\n已进入窗口「{session.name}」")
    print("输入 /back 返回菜单, 输入 /quit 退出程序\n")

    while True:
        try:
            user_input = input(f"[{session.name}] > ").strip() 
            # .strip() —— 去掉字符串开头和结尾的空白字符，返回一个新的字符串
        except EOFError:
            print() # 输出一个空行
            return True
        except KeyboardInterrupt:
            # 终端按 Ctrl+C 时，Python 会抛出 KeyboardInterrupt 异常
            print("\n(/back 返回菜单, /quit 退出程序)")
            continue

        if not user_input:
            continue
        if user_input == "/back":
            return True
        if user_input == "/quit":
            return False

        agent_run(user_input, session)
        print()


def main_menu():
    while True:
        sessions = manager.list_sessions()
        print("\n========== 会话窗口 ==========")
        for i, s in enumerate(sessions, start=1):
            print(f"  {i}. {s.name}({len(s.messages)} 条消息)")
        print("  n. 新建窗口")
        print("  q. 退出程序")
        print("==============================")

        try:
            choice = input("请选择 > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "q":
            break
        elif choice == "n":
            try:
                name = input("窗口名称(回车使用默认)> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            session = manager.create(name or None)
            if not open_session(session):
                break
        elif choice.isdigit() and 1 <= int(choice) <= len(sessions):
            session = sessions[int(choice) - 1]
            if not open_session(session):
                break
        else:
            print("无效选择, 请重新输入")

    print("再见!")

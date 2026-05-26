"""
main.py — KakaoAdmin 진입점
Crafted by IDO(idocho@kakao.com) · Powered by Claude AI
"""
import tkinter as tk
from app import KakaoAdminApp


def main():
    root = tk.Tk()
    KakaoAdminApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

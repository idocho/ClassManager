"""
main.py — ClassManager 진입점
Crafted by IDO(idocho@kakao.com) · Powered by Claude AI
"""
import tkinter as tk
from app import ClassManagerApp


def main():
    root = tk.Tk()
    ClassManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

from flask import Blueprint, redirect, render_template, request, url_for

from app import gemini_chat

bp = Blueprint("chat", __name__, url_prefix="/chat")


@bp.route("/")
def chat_view():
    history = gemini_chat.get_history()
    return render_template("chat.html", history=history, error=request.args.get("error"))


@bp.route("/send", methods=["POST"])
def send():
    text = request.form.get("message", "")
    try:
        gemini_chat.send_message(text)
    except gemini_chat.ChatError as exc:
        return redirect(url_for("chat.chat_view", error=str(exc)))
    return redirect(url_for("chat.chat_view"))

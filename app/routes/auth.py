from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """用户注册。"""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password:
            flash("用户名和密码不能为空。", "danger")
            return render_template("register.html")

        if len(password) < 4:
            flash("密码长度至少为 4 位。", "danger")
            return render_template("register.html")

        if password != confirm:
            flash("两次输入的密码不一致。", "danger")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("用户名已存在。", "danger")
            return render_template("register.html")

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("注册成功，请登录。", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """用户登录。"""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("用户名或密码错误。", "danger")
            return render_template("login.html")

        login_user(user, remember=True)
        next_page = request.args.get("next")
        flash(f"欢迎回来，{username}！", "success")
        return redirect(next_page or url_for("main.index"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """用户退出。"""
    logout_user()
    flash("您已退出登录。", "info")
    return redirect(url_for("main.index"))

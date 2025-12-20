#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from printfleet.db import (
    count_users,
    create_user,
    get_user_by_id,
    get_user_by_username,
    update_user_password,
)
from printfleet.i18n import _

from . import bp


@bp.route("/login", methods=["GET", "POST"])
def login() -> str:
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    first_user = count_users() == 0

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash(_("login_error_required"), "danger")
            return render_template("login.html", first_user=first_user, page="login")

        if first_user:
            password_confirm = request.form.get("password_confirm") or ""
            if password != password_confirm:
                flash(_("login_error_password_mismatch"), "danger")
                return render_template("login.html", first_user=first_user, page="login")

            try:
                user_id = create_user(username, generate_password_hash(password))
            except sqlite3.IntegrityError:
                flash(_("login_error_username_exists"), "danger")
                return render_template("login.html", first_user=first_user, page="login")

            session["user_id"] = user_id
            session["username"] = username
            flash(_("login_success_created"), "success")
            return redirect(url_for("dashboard.index"))

        user = get_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            flash(_("login_error_invalid"), "danger")
            return render_template("login.html", first_user=first_user, page="login")

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("dashboard.index"))

    return render_template("login.html", first_user=first_user, page="login")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
def profile() -> str:
    user_id = session.get("user_id")
    user = get_user_by_id(int(user_id)) if user_id else None

    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not current_password or not new_password or not confirm_password:
            flash(_("profile_error_required"), "danger")
            return render_template("profile.html", page="profile", user=user)

        if not check_password_hash(user["password_hash"], current_password):
            flash(_("profile_error_wrong_password"), "danger")
            return render_template("profile.html", page="profile", user=user)

        if new_password != confirm_password:
            flash(_("profile_error_password_mismatch"), "danger")
            return render_template("profile.html", page="profile", user=user)

        update_user_password(user["id"], generate_password_hash(new_password))
        flash(_("profile_password_updated"), "success")

    return render_template("profile.html", page="profile", user=user)

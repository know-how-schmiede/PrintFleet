#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import render_template
from markupsafe import Markup, escape

try:
    import bleach
    import markdown
except Exception:
    bleach = None
    markdown = None

from printfleet.db import load_settings_from_db

from . import bp


@bp.route("/imprint")
def imprint() -> str:
    settings = load_settings_from_db()
    imprint_md = settings.get("imprint_markdown") or ""
    imprint_html = _render_markdown(imprint_md)
    return render_template(
        "imprint.html",
        page="imprint",
        imprint_html=imprint_html,
        has_imprint=bool(imprint_md.strip()),
    )


@bp.route("/privacy")
def privacy() -> str:
    settings = load_settings_from_db()
    privacy_md = settings.get("privacy_markdown") or ""
    privacy_html = _render_markdown(privacy_md)
    return render_template(
        "privacy.html",
        page="privacy",
        privacy_html=privacy_html,
        has_privacy=bool(privacy_md.strip()),
    )


def _render_markdown(text: str) -> Markup:
    if not markdown or not bleach:
        return Markup(f"<pre>{escape(text or '')}</pre>")

    html = markdown.markdown(
        text or "",
        extensions=["extra", "sane_lists", "tables"],
        output_format="html",
    )

    allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
        "p",
        "pre",
        "span",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "code",
        "hr",
        "br",
        "ul",
        "ol",
        "li",
        "blockquote",
    ]
    allowed_attrs = {
        "a": ["href", "title", "rel", "target"],
        "code": ["class"],
    }
    allowed_protocols = ["http", "https", "mailto"]

    cleaned = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=allowed_protocols,
        strip=True,
    )
    cleaned = bleach.linkify(cleaned)
    return Markup(cleaned)

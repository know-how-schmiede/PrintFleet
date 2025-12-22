#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import render_template
from html.parser import HTMLParser
from html import escape as html_escape
import re

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
    linked = _linkify_html(cleaned)
    return Markup(linked)


_EMAIL_RE = re.compile(
    r"(?<![\\w@])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,})(?![\\w@])"
)
_URL_RE = re.compile(r"(https?://[^\\s<]+)", re.IGNORECASE)
_SKIP_TAGS = {"a", "pre", "code"}


def _strip_trailing_punct(value: str) -> tuple[str, str]:
    trailing = ""
    while value and value[-1] in ".,);:":
        trailing = value[-1] + trailing
        value = value[:-1]
    return value, trailing


def _linkify_text(text: str) -> str:
    def repl_email(match: re.Match) -> str:
        email = match.group(1)
        return f'<a href="mailto:{email}">{email}</a>'

    def repl_url(match: re.Match) -> str:
        url = match.group(1)
        url, trailing = _strip_trailing_punct(url)
        return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>{trailing}'

    text = _EMAIL_RE.sub(repl_email, text)
    text = _URL_RE.sub(repl_url, text)
    return text


class _LinkifyHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        self._parts.append(self._format_starttag(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            self._parts.append(data)
        else:
            self._parts.append(_linkify_text(data))

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._parts.append(self._format_starttag(tag, attrs, close_empty=True))

    def get_html(self) -> str:
        return "".join(self._parts)

    def _format_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        close_empty: bool = False,
    ) -> str:
        if not attrs:
            return f"<{tag}{' /' if close_empty else ''}>"

        rendered = []
        for key, value in attrs:
            if value is None:
                rendered.append(f" {key}")
            else:
                rendered.append(f' {key}="{html_escape(value, quote=True)}"')
        return f"<{tag}{''.join(rendered)}{' /' if close_empty else ''}>"


def _linkify_html(html: str) -> str:
    parser = _LinkifyHTML()
    parser.feed(html)
    parser.close()
    return parser.get_html()

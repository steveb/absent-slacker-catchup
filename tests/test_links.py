"""Tests for hyperlinking bare URLs."""

from __future__ import annotations

from asc.links import linkify_markdown, linkify_text


def test_linkify_text_wraps_a_url():
    html = linkify_text("see https://example.com/a for details")
    assert (
        '<a href="https://example.com/a" rel="nofollow noopener">'
        "https://example.com/a</a>" in html
    )


def test_linkify_text_handles_several_urls():
    html = linkify_text("https://a.example/x and https://b.example/y")
    assert html.count("<a href=") == 2


def test_linkify_text_trims_sentence_punctuation():
    html = linkify_text("look at https://example.com/bug, then https://example.com/x.")
    assert 'href="https://example.com/bug"' in html
    assert 'href="https://example.com/x"' in html
    assert html.count("</a>,") == 1


def test_linkify_text_keeps_balanced_brackets():
    html = linkify_text("https://example.com/wiki/Foo_(bar)")
    assert 'href="https://example.com/wiki/Foo_(bar)"' in html


def test_linkify_text_escapes_html():
    html = linkify_text("<script>alert('x')</script> https://example.com/?a=1&b=2")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="https://example.com/?a=1&amp;b=2"' in html


def test_linkify_text_ignores_non_http_schemes():
    html = linkify_text("javascript:alert(1) and ftp://example.com")
    assert "<a" not in html


def test_linkify_markdown_wraps_bare_urls():
    assert linkify_markdown("see https://example.com/a now") == (
        "see <https://example.com/a> now"
    )


def test_linkify_markdown_leaves_existing_links_alone():
    text = "[review](https://review.example/1) or <https://auto.example/2>"
    assert linkify_markdown(text) == text


def test_linkify_markdown_skips_code():
    text = "`https://inline.example`\n\n```\nhttps://fenced.example\n```"
    assert linkify_markdown(text) == text


def test_linkify_markdown_is_rendered_by_markdown():
    from asc.render import summary_to_html

    html = summary_to_html("See https://review.opendev.org/c/openstack/ironic/+/1")
    assert '<a href="https://review.opendev.org/c/openstack/ironic/+/1">' in html

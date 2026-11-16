"""Tests for hyperlinking bare URLs."""

from __future__ import annotations

from asc.links import (
    launchpad_project_for,
    linkify_markdown,
    linkify_references,
    linkify_text,
)


def test_linkify_text_wraps_a_url():
    html = linkify_text("see https://example.com/a for details")
    assert (
        '<a href="https://example.com/a" rel="nofollow noopener" '
        'target="_blank">https://example.com/a</a>' in html
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
    assert '<a href="https://review.opendev.org/c/openstack/ironic/+/1"' in html
    assert 'target="_blank"' in html


def test_linkify_references_links_review_numbers():
    text = "Ironic change 1013352 and openstacksdk review 1015357"

    linked = linkify_references(text)

    assert (
        "change [1013352](https://review.opendev.org/c/1013352)" in linked
    )
    assert (
        "review [1015357](https://review.opendev.org/c/1015357)" in linked
    )


def test_linkify_references_links_bug_numbers():
    linked = linkify_references("Launchpad bug 2123456", launchpad_project="ironic")

    assert (
        "bug [2123456](https://bugs.launchpad.net/ironic/+bug/2123456)" in linked
    )


def test_linkify_references_keeps_hash_in_link_text():
    linked = linkify_references("bug #2123456")

    assert "[#2123456](https://bugs.launchpad.net/bugs/2123456)" in linked


def test_linkify_references_skips_code_existing_links_and_urls():
    text = (
        "`bug 2123456` and [change 1013352](https://example.com/x) and "
        "https://example.com/bug/2123456"
    )

    assert linkify_references(text) == text


def test_linkify_references_ignores_short_numbers():
    text = "2026, patch set 3 and 1013352 on its own"

    assert linkify_references(text) == text


def test_launchpad_project_for_channel():
    assert launchpad_project_for("#openstack-ironic") == "ironic"
    assert launchpad_project_for("#tripleo") is None
    assert launchpad_project_for(None) is None

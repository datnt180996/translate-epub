"""Unit tests cho parser 69shuba và chapter_cleaner."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chapter_cleaner import (
    clean_html_to_text,
    chunk_text,
    join_paragraphs,
    split_into_paragraphs,
)
from app.services.web_importer import (
    parse_69shuba_index,
    parse_chapter_text,
    parse_generic_index,
)
from app.services.web_importer import _decode_html, _69shuba_catalog_url


SAMPLE_69SHUBA_INDEX = """
<!DOCTYPE html>
<html>
<head><meta charset="gb18030"><title>飞剑问道-69书吧</title></head>
<body>
<div class="bookinfo">
  <div class="info">
    <h1>飞剑问道</h1>
    <p><span>作者：耳根</span></p>
    <p><span>状态：连载中</span></p>
  </div>
  <div id="fmimg"><img src="https://cdn.cdnshu.com/files/article/image/51/51256/51256s.jpg" alt="cover"></div>
  <div id="intro">这是一本修仙小说。</div>
</div>
<div id="list">
  <ul>
    <li><a href="/txt/51256/10001">第一章 少年</a></li>
    <li><a href="/txt/51256/10002">第二章 灵气</a></li>
    <li><a href="/txt/51256/10003">第三章 修炼</a></li>
    <li><a href="/book/51256/4.html">第四章 突破</a></li>
  </ul>
</div>
</body>
</html>
"""


SAMPLE_69SHUBA_CHAPTER = """
<!DOCTYPE html>
<html>
<head><title>第一章 少年 - 69书吧</title></head>
<body>
<div class="header"><a href="/">首页</a></div>
<div class="txtnav">
第一章 少年<br/>
少年名叫李云，是个普通农家子弟。<br/>
这一天，他在山上砍柴时发现了一块奇怪的石头。<br/>
石头散发着淡淡的光芒。
</div>
<div class="footer">首页 书页 收藏 目录 设置 白天</div>
</body>
</html>
"""


def test_clean_html_strips_scripts_and_nav():
    html = """
    <html><head><script>alert('x')</script></head><body>
      <nav>menu</nav>
      <p>Đoạn một.</p>
      <p>Đoạn hai.</p>
      <script>foo()</script>
    </body></html>
    """
    text = clean_html_to_text(html)
    assert "Đoạn một." in text
    assert "Đoạn hai." in text
    assert "alert" not in text
    assert "foo()" not in text
    assert "menu" not in text


def test_split_and_join_roundtrip():
    text = "A.\n\nB.\n\nC."
    paras = split_into_paragraphs(text)
    assert paras == ["A.", "B.", "C."]
    assert join_paragraphs(paras) == text


def test_chunk_short():
    chunks = chunk_text("Đoạn một.\n\nĐoạn hai.", max_chars=1000)
    assert chunks == ["Đoạn một.\n\nĐoạn hai."]


def test_chunk_long_splits():
    paras = [f"Đoạn {i}.\n" * 5 for i in range(50)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, max_chars=200)
    assert len(chunks) > 1
    joined = "\n\n".join(chunks)
    assert "Đoạn 0." in joined
    assert "Đoạn 49." in joined


def test_chunk_oversized_paragraph_splits_by_sentence():
    long = "少年名叫李云。 " * 200
    chunks = chunk_text(long, max_chars=120)
    assert len(chunks) > 1
    for c in chunks:
        assert "少年名叫李云。" in c
        assert len(c) <= 200
    joined = "".join(chunks)
    assert joined.count("少年名叫李云。") >= 198


def test_parse_69shuba_index_extracts_title_and_chapters():
    novel = parse_69shuba_index(SAMPLE_69SHUBA_INDEX, "https://www.69shuba.com/book/51256.htm")
    assert novel.title == "飞剑问道"
    assert novel.description == "这是一本修仙小说。"
    assert novel.author == "耳根"
    assert novel.cover_url == "https://cdn.cdnshu.com/files/article/image/51/51256/51256s.jpg"
    assert len(novel.chapters) == 4
    assert novel.chapters[0].title == "第一章 少年"
    assert novel.chapters[0].url == "https://www.69shuba.com/txt/51256/10001"
    assert novel.chapters[2].url == "https://www.69shuba.com/txt/51256/10003"
    assert novel.chapters[3].url == "https://www.69shuba.com/book/51256/4.html"


def test_parse_chapter_text_extracts_content():
    text = parse_chapter_text(SAMPLE_69SHUBA_CHAPTER)
    assert "少年名叫李云" in text
    assert "石头散发着淡淡的光芒" in text
    assert "底部导航" not in text
    assert "首页" not in text


def test_parse_generic_index_fallback():
    html = """
    <html><head><title>Generic Novel</title></head><body>
      <a href="/ch/1.html">Chương 1</a>
      <a href="/ch/2.html">Chương 2</a>
      <a href="/about">Giới thiệu</a>
    </body></html>
    """
    novel = parse_generic_index(html, "https://example.com/book")
    assert novel.title == "Generic Novel"
    assert novel.author is None
    assert novel.cover_url is None
    assert len(novel.chapters) == 2
    assert novel.chapters[0].url == "https://example.com/ch/1.html"


def test_decode_html_utf8():
    text = _decode_html("<title>tiêu đề</title>".encode("utf-8"))
    assert "tiêu đề" in text


def test_decode_html_gbk_uses_meta_charset():
    html = (
        '<html><head><meta charset="gb18030"><title>飞剑</title></head>'
        '<body><a href="/txt/51256/1">少年</a></body></html>'
    )
    encoded = html.encode("gb18030")
    text = _decode_html(encoded, "text/html")
    assert "飞剑" in text
    assert "少年" in text


def test_69shuba_catalog_url_from_book_page():
    out = _69shuba_catalog_url("https://www.69shuba.com/book/51256.htm")
    assert out == "https://www.69shuba.com/book/51256/"


def test_69shuba_catalog_url_already_catalog():
    out = _69shuba_catalog_url("https://www.69shuba.com/book/51256/")
    assert out == "https://www.69shuba.com/book/51256/"


if __name__ == "__main__":
    tests = [
        test_clean_html_strips_scripts_and_nav,
        test_split_and_join_roundtrip,
        test_chunk_short,
        test_chunk_long_splits,
        test_chunk_oversized_paragraph_splits_by_sentence,
        test_parse_69shuba_index_extracts_title_and_chapters,
        test_parse_chapter_text_extracts_content,
        test_parse_generic_index_fallback,
        test_decode_html_utf8,
        test_decode_html_gbk_uses_meta_charset,
        test_69shuba_catalog_url_from_book_page,
        test_69shuba_catalog_url_already_catalog,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
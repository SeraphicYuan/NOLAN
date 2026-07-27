"""The lexical channel over the transcript library — honesty tests.

Every test here is a claim `docs/VIDEO_RETRIEVAL_PROGRAM.md` makes about this module. They run
against a SYNTHETIC index (rows inserted straight into a temp db) rather than the real library, so
they assert the retrieval PROPERTY and not today's corpus.
"""
import pytest

from nolan import transcript_fts as fts


def _mk(tmp_path, rows):
    """A tiny lexical index: rows are (kind, video_id, url, start, title, text)."""
    db = tmp_path / "lex.db"
    conn = fts._connect(db)
    conn.executemany(
        'INSERT INTO lex (kind, video_id, url, start, "end", ref, title, text) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(k, v, u, s, s + 5, f"{k}:{i}", ti, tx)
         for i, (k, v, u, s, ti, tx) in enumerate(rows)])
    conn.commit()
    conn.close()
    return db


DIAMOND = [
    ("frame", "v1", "https://x/1", 42.0, "The Real Reason We Buy Diamonds",
     "a historical portrait of Englishman Cecil Rhodes as the narrator discusses De Beers"),
    ("segment", "v1", "https://x/1", 220.0, "The Real Reason We Buy Diamonds",
     "increasing the chance for De Beers to sell more freshly mined stones"),
    ("frame", "v2", "https://x/2", 570.0, "South Dakota Saga",
     "a wide view of an open pit coal mine where dirt is extracted by machinery"),
]


def test_tokens_drop_stopwords_and_query_noise():
    """'footage' / 'shot' / 'clip' are content words in a film catalogue and pure noise in a b-roll
    query — matching them would hand back the whole corpus and destroy the abstain signal."""
    toks = fts._tokens("a close-up shot of the archival footage clip showing Cecil Rhodes")
    assert "cecil" in toks and "rhodes" in toks
    for noise in ("the", "of", "shot", "footage", "clip", "close", "showing"):
        assert noise not in toks


def test_match_expr_is_or_not_and():
    """A b-roll query is a sentence; no single document holds every token, so AND would abstain on
    everything and the channel would be dead."""
    expr = fts._match_expr("1970s courtroom wood panelling")
    assert " OR " in expr and " AND " not in expr


def test_match_expr_survives_quotes_and_punctuation():
    """`De Beers v. United States (2004)` must not break the MATCH parse."""
    db_expr = fts._match_expr('De Beers v. "United" States (2004)')
    assert db_expr and '"' in db_expr
    assert "(" not in db_expr.replace('"', "")   # punctuation stripped, not passed through


def test_stem_matches_plural_to_singular():
    """The index stems (porter); a Python-side comparison must too, or coverage under-counts
    exactly the rare tokens it depends on."""
    assert fts._stem("penguins") == fts._stem("penguin")
    assert fts._stem("mines") == fts._stem("mine")


def test_named_query_finds_the_entity(tmp_path):
    db = _mk(tmp_path, DIAMOND)
    hits = fts.search("Cecil Rhodes", k=3, db=db)
    assert hits and "Cecil Rhodes" in hits[0]["text"]


def test_title_is_weighted_above_body(tmp_path):
    """The film title is the identity signal, and it is the one field NEITHER dense index sees."""
    db = _mk(tmp_path, [
        ("segment", "v1", "u1", 0.0, "The Kimberley Mine Story", "a narrator introduces the film"),
        ("segment", "v2", "u2", 0.0, "Unrelated Newsreel",
         "kimberley is mentioned once in passing here"),
    ])
    hits = fts.search("Kimberley", k=2, db=db)
    assert hits[0]["title"] == "The Kimberley Mine Story"


def test_absent_term_is_reported_missing(tmp_path):
    """The abstain signal: a term that occurs NOWHERE is evidence of absence — the thing a
    k-nearest index can never say. Measured on the real library, 'Lightbox Jewelry' scores 0.35
    with `lightbox` missing, where the dense channel returned lightning stock at 0.680."""
    db = _mk(tmp_path, DIAMOND)
    s = fts.support("Lightbox Jewelry", db=db)
    assert "lightbox" in s["missing"]
    assert s["cover"] < 0.5
    assert not fts.has_support("Lightbox Jewelry", db=db)


def test_support_is_per_document_not_corpus_wide(tmp_path):
    """THE regression test. Corpus-level coverage scored 'hands knitting a wool scarf' at 1.000
    against a library holding no knitting at all, because `knit`, `wool` and `scarf` each turned up
    in three unrelated films. Support means ONE document covers the query."""
    db = _mk(tmp_path, [
        ("frame", "v1", "u1", 0.0, "Kent State", "a person wearing a cable knit sweater"),
        ("frame", "v2", "u2", 0.0, "Textile Mill", "bales of raw wool arrive at the mill"),
        ("frame", "v3", "u3", 0.0, "Winter Fashion", "a silk scarf on a mannequin"),
        ("frame", "v4", "u4", 0.0, "Radio Assembly", "a worker's hands solder a circuit board"),
    ])
    s = fts.support("hands knitting a wool scarf", db=db)
    assert s["corpus_cover"] > 0.9        # every term exists SOMEWHERE
    assert s["cover"] < 0.6               # ...but no single document covers the query
    assert not fts.has_support("hands knitting a wool scarf", db=db)


def test_on_domain_query_has_support(tmp_path):
    db = _mk(tmp_path, DIAMOND)
    assert fts.has_support("open pit mine machinery", db=db)


def test_empty_query_abstains_rather_than_matching_everything(tmp_path):
    """A query of nothing but stop-words must return [], not the whole corpus."""
    db = _mk(tmp_path, DIAMOND)
    assert fts.search("the a of in", k=5, db=db) == []
    assert fts.support("the a of in", db=db)["cover"] == 0.0


def test_kind_filter_separates_the_two_tiers(tmp_path):
    db = _mk(tmp_path, DIAMOND)
    assert all(h["kind"] == "frame" for h in fts.search("De Beers mine", k=9, kind="frame", db=db))
    assert all(h["kind"] == "segment"
               for h in fts.search("De Beers mine", k=9, kind="segment", db=db))


def test_field_scoped_query_searches_titles_only(tmp_path):
    """Identity anchoring for keyassets Tier B: match the entity against TITLES, where a hit means
    the film is ABOUT the entity rather than mentioning it once."""
    db = _mk(tmp_path, DIAMOND)
    assert fts.search("Dakota", k=5, fields="title", db=db)
    assert not fts.search("machinery", k=5, fields="title", db=db)   # body-only term


def test_stats_reports_both_tiers(tmp_path):
    db = _mk(tmp_path, DIAMOND)
    s = fts.stats(db=db)
    assert s["total"] == 3 and s["frame"] == 2 and s["segment"] == 1

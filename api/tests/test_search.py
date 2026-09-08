"""Typed-search helpers: folding and the Lucene query built from a search box string."""
from illuminate.ids import fold_text, lucene_query, search_tokens


def test_fold_is_case_accent_and_punctuation_insensitive():
    assert fold_text("Société L-3 Harris, Inc.") == "societe l 3 harris inc"
    assert fold_text("  PAMELA   a. Wickham ") == "pamela a wickham"
    assert search_tokens("Raytheon/Technologies") == ["raytheon", "technologies"]
    assert search_tokens("") == [] and search_tokens("  ... ") == []


def test_lucene_query_requires_every_word_with_prefix_and_fuzzy():
    assert lucene_query("pame") == "(pame OR pame* OR pame~1)"
    assert lucene_query("Pamela Wickham") == "(pamela OR pamela* OR pamela~1) AND (wickham OR wickham* OR wickham~1)"


def test_lucene_query_short_words_are_prefix_only_and_syntax_is_neutralised():
    # a fuzzy "a~1" would match nearly everything; short tokens only prefix-match
    assert lucene_query("a") == "(a OR a*)"
    # Lucene operators typed by the user never reach the query
    q = lucene_query('(bad "syntax) AND +x -y ~ *')
    assert q == "(bad OR bad*) AND (syntax OR syntax* OR syntax~1) AND (and OR and*) AND (x OR x*) AND (y OR y*)"
    assert lucene_query("") == ""

"""Shared rank/quartile helper used by transformers that need per-cohort
class rank and quartile on a score column.
"""

import pandas as pd


def add_rank_and_quartile(
    df: pd.DataFrame, score_col: str, name: str, group_cols: list[str]
) -> pd.DataFrame:
    """
    Add class rank and quartile for a score column, calculated within each
    group_cols cohort.

    Rank 1 = highest score. Quartile 4 = top 25%.
    Rows with no score receive NaN for both.

    Args:
        score_col:  Column to rank on (e.g. 'reading_composite_score')
        name:       Prefix for output columns (e.g. 'reading_composite')
        group_cols: Columns defining the cohort to rank within
    """
    rank_col = f"{name}_class_rank"
    quartile_col = f"{name}_quartile"

    df[rank_col] = (
        df.groupby(group_cols)[score_col]
        .rank(method="min", ascending=False, na_option="keep")
        .astype("Int64")
    )

    pct_rank = df.groupby(group_cols)[score_col].rank(
        pct=True, ascending=False, na_option="keep"
    )
    df[quartile_col] = pd.cut(
        pct_rank,
        bins=[0, 0.25, 0.5, 0.75, 1.0],
        labels=[4, 3, 2, 1],
        include_lowest=True,
    ).astype("Int64")

    return df

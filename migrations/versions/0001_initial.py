"""initial schema"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    op.create_table(
        "points_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("exact_points", sa.Integer, nullable=False, server_default="5"),
        sa.Column("result_points", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.execute(
        "INSERT INTO points_rules (id, exact_points, result_points) VALUES (1, 5, 1) "
        "ON CONFLICT (id) DO NOTHING"
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("team1", sa.Text, nullable=False),
        sa.Column("team2", sa.Text, nullable=False),
        sa.Column("score1", sa.Integer),
        sa.Column("score2", sa.Integer),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_matches_status", "matches", ["status"])

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "predictions",
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("match_id", sa.BigInteger, sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("pred_score1", sa.Integer, nullable=False),
        sa.Column("pred_score2", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_predictions_user", "predictions", ["user_id"])
    op.create_index("ix_predictions_match", "predictions", ["match_id"])

    op.execute(
        """
        CREATE MATERIALIZED VIEW leaderboard AS
        WITH rules AS (
            SELECT exact_points, result_points FROM points_rules WHERE id = 1
        )
        SELECT
            p.user_id,
            COALESCE(SUM(
                CASE
                    WHEN m.status = 'finished' AND m.score1 IS NOT NULL AND m.score2 IS NOT NULL THEN
                        CASE
                            WHEN p.pred_score1 = m.score1 AND p.pred_score2 = m.score2 THEN rules.exact_points
                            WHEN (p.pred_score1 - p.pred_score2) = (m.score1 - m.score2)
                                 OR SIGN(p.pred_score1 - p.pred_score2) = SIGN(m.score1 - m.score2)
                            THEN rules.result_points
                            ELSE 0
                        END
                    ELSE 0
                END
            ), 0) AS points
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        CROSS JOIN rules
        GROUP BY p.user_id;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS leaderboard_user_id_idx ON leaderboard(user_id);"
    )


def downgrade():
    op.execute("DROP MATERIALIZED VIEW IF EXISTS leaderboard;")
    op.drop_index("ix_predictions_match", table_name="predictions")
    op.drop_index("ix_predictions_user", table_name="predictions")
    op.drop_table("predictions")
    op.drop_table("users")
    op.drop_index("ix_matches_status", table_name="matches")
    op.drop_table("matches")
    op.drop_table("points_rules")

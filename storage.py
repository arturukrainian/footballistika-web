from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_POOL_URL") or os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


class Base(DeclarativeBase):
    pass


class PointsRule(Base):
    __tablename__ = "points_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    exact_points: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    result_points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("status in ('scheduled','live','finished')", name="chk_match_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team1: Mapped[str] = mapped_column(Text, nullable=False)
    team2: Mapped[str] = mapped_column(Text, nullable=False)
    score1: Mapped[Optional[int]] = mapped_column(Integer)
    score2: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scheduled")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    predictions: Mapped[List["Prediction"]] = relationship(back_populates="match")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    predictions: Mapped[List["Prediction"]] = relationship(back_populates="user")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint("pred_score1 >= 0"),
        CheckConstraint("pred_score2 >= 0"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    pred_score1: Mapped[int] = mapped_column(Integer, nullable=False)
    pred_score2: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="predictions")
    match: Mapped[Match] = relationship(back_populates="predictions")


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_rules(session: Session) -> PointsRule:
    rules = session.get(PointsRule, 1)
    if not rules:
        rules = PointsRule(id=1, exact_points=5, result_points=1)
        session.add(rules)
        session.commit()
    return rules


def ensure_user_record(user_id: int, username: str) -> None:
    with session_scope() as session:
        user = session.get(User, user_id)
        if not user:
            session.add(User(id=user_id, username=username))
            return
        if username and user.username != username:
            user.username = username


def add_match(team1: str, team2: str, started_at: Optional[datetime] = None) -> Dict:
    with session_scope() as session:
        match = Match(team1=team1, team2=team2, status="scheduled", started_at=started_at)
        session.add(match)
        session.flush()
        return _match_to_dict(match)


def upsert_match(match_id: int, team1: str, team2: str, status: str, score1=None, score2=None) -> Dict:
    with session_scope() as session:
        match = session.get(Match, match_id)
        if not match:
            match = Match(
                id=match_id,
                team1=team1,
                team2=team2,
                status=status,
                score1=score1,
                score2=score2,
            )
            session.add(match)
        else:
            if match.status == "finished" and (match.team1 != team1 or match.team2 != team2):
                raise ValueError("Cannot change teams of finished match")
            match.team1 = team1
            match.team2 = team2
            match.status = status
            match.score1 = score1
            match.score2 = score2
            match.updated_at = datetime.utcnow()
        session.flush()
        return _match_to_dict(match)


def find_match(match_id: int) -> Optional[Dict]:
    with session_scope() as session:
        match = session.get(Match, match_id)
        return _match_to_dict(match) if match else None


def get_next_pending_match_for_result() -> Optional[Dict]:
    with session_scope() as session:
        match = session.scalars(
            select(Match).where(Match.status != "finished").order_by(Match.id)
        ).first()
        return _match_to_dict(match) if match else None


def update_match_result(match_id: int, score1: int, score2: int) -> Optional[Dict]:
    with session_scope() as session:
        match = session.get(Match, match_id)
        if not match:
            return None
        match.score1 = score1
        match.score2 = score2
        match.status = "finished"
        match.updated_at = datetime.utcnow()
        session.flush()
        return _match_to_dict(match)


def get_next_match_for_prediction(user_id: int) -> Optional[Dict]:
    with session_scope() as session:
        sub = select(Prediction.match_id).where(Prediction.user_id == user_id)
        match = session.scalars(
            select(Match).where(Match.status == "scheduled", Match.id.not_in(sub)).order_by(Match.id)
        ).first()
        return _match_to_dict(match) if match else None


def get_pending_matches_for_user(user_id: int) -> List[Dict]:
    with session_scope() as session:
        sub = select(Prediction.match_id).where(Prediction.user_id == user_id)
        matches = session.scalars(
            select(Match).where(Match.status == "scheduled", Match.id.not_in(sub)).order_by(Match.id)
        ).all()
        return [_match_to_dict(m) for m in matches]


def get_pending_matches_with_user_predictions(user_id: int) -> List[Dict]:
    with session_scope() as session:
        matches = session.scalars(
            select(Match).where(Match.status == "scheduled").order_by(Match.id)
        ).all()
        predictions = {
            p.match_id: p
            for p in session.scalars(
                select(Prediction).where(Prediction.user_id == user_id, Prediction.match_id.in_([m.id for m in matches]))
            ).all()
        }
        result = []
        for match in matches:
            pred = predictions.get(match.id)
            result.append(
                {
                    "id": match.id,
                    "team1": match.team1,
                    "team2": match.team2,
                    "predicted": bool(pred),
                    "pred_score1": pred.pred_score1 if pred else None,
                    "pred_score2": pred.pred_score2 if pred else None,
                }
            )
        return result


def append_prediction(match_id: int, user_id: int, username: str, score1: int, score2: int) -> None:
    with session_scope() as session:
        _ensure_user(session, user_id, username)
        prediction = Prediction(
            user_id=user_id,
            match_id=match_id,
            pred_score1=score1,
            pred_score2=score2,
        )
        session.add(prediction)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise ValueError("prediction_exists")


def get_user_prediction(match_id: int, user_id: int) -> Optional[Dict]:
    with session_scope() as session:
        prediction = session.get(Prediction, {"user_id": user_id, "match_id": match_id})
        if not prediction:
            return None
        return _prediction_to_dict(prediction)


def read_predictions() -> List[Dict]:
    with session_scope() as session:
        preds = session.scalars(select(Prediction)).all()
        return [_prediction_to_dict(p) for p in preds]


def read_matches() -> List[Dict]:
    with session_scope() as session:
        matches = session.scalars(select(Match).order_by(Match.id)).all()
        return [_match_to_dict(m) for m in matches]


def settle_match_points(match_id: int, score1: int, score2: int) -> List[Tuple[int, str, int]]:
    with session_scope() as session:
        rules = _get_rules(session)
        predictions = session.scalars(select(Prediction).where(Prediction.match_id == match_id)).all()
        awarded: List[Tuple[int, str, int]] = []
        for pred in predictions:
            points = _calculate_points(rules, score1, score2, pred.pred_score1, pred.pred_score2)
            user = session.get(User, pred.user_id)
            username = user.username if user else ""
            awarded.append((pred.user_id, username, points))
        return awarded


def leaderboard_rows() -> List[Tuple[int, str, int]]:
    refresh_leaderboard()
    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT l.user_id, u.username, l.points "
                "FROM leaderboard l LEFT JOIN users u ON u.id=l.user_id "
                "ORDER BY l.points DESC"
            )
        ).all()
        return [(row.user_id, row.username, int(row.points or 0)) for row in rows]


def average_predictions_per_match(include_finished: bool = True) -> List[Dict]:
    with session_scope() as session:
        stmt = (
            select(
                Prediction.match_id,
                func.avg(Prediction.pred_score1).label("avg1"),
                func.avg(Prediction.pred_score2).label("avg2"),
                func.count(Prediction.user_id).label("count"),
            )
            .join(Match, Match.id == Prediction.match_id)
        )
        if not include_finished:
            stmt = stmt.where(Match.status != "finished")
        stmt = stmt.group_by(Prediction.match_id).order_by(Prediction.match_id)
        rows = session.execute(stmt).all()
        result = []
        for row in rows:
            match = session.get(Match, row.match_id)
            if not match:
                continue
            result.append(
                {
                    "match": _match_to_dict(match),
                    "avg1": row.avg1,
                    "avg2": row.avg2,
                    "count": row.count,
                }
            )
        return result


def read_prediction_result_accuracy() -> List[Dict]:
    with session_scope() as session:
        rules = _get_rules(session)
        rows = session.execute(
            text(
                """
                SELECT
                    p.user_id,
                    u.username,
                    COUNT(*) AS predictions,
                    SUM(
                        CASE
                            WHEN m.status='finished' AND m.score1 IS NOT NULL AND m.score2 IS NOT NULL
                                 AND SIGN(p.pred_score1 - p.pred_score2) = SIGN(m.score1 - m.score2)
                            THEN 1 ELSE 0 END
                    )::float / NULLIF(COUNT(*),0) * 100 AS result_accuracy_percent
                FROM predictions p
                JOIN matches m ON m.id = p.match_id
                LEFT JOIN users u ON u.id = p.user_id
                WHERE m.status='finished'
                GROUP BY p.user_id, u.username
                """
            )
        ).all()
        return [
            {
                "user_id": row.user_id,
                "username": row.username,
                "predictions": int(row.predictions),
                "result_accuracy_percent": float(row.result_accuracy_percent or 0.0),
            }
            for row in rows
        ]


def read_prediction_goal_accuracy() -> List[Dict]:
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    p.user_id,
                    u.username,
                    COUNT(*) AS predictions,
                    AVG(100 - 100 * ABS(p.pred_score1 - m.score1) / NULLIF(GREATEST(p.pred_score1, m.score1),1)) AS acc1,
                    AVG(100 - 100 * ABS(p.pred_score2 - m.score2) / NULLIF(GREATEST(p.pred_score2, m.score2),1)) AS acc2
                FROM predictions p
                JOIN matches m ON m.id = p.match_id
                LEFT JOIN users u ON u.id = p.user_id
                WHERE m.status='finished' AND m.score1 IS NOT NULL AND m.score2 IS NOT NULL
                GROUP BY p.user_id, u.username
                """
            )
        ).all()
        result = []
        for row in rows:
            goal_accuracy = ((row.acc1 or 0.0) + (row.acc2 or 0.0)) / 2
            result.append(
                {
                    "user_id": row.user_id,
                    "username": row.username,
                    "predictions": int(row.predictions),
                    "goal_accuracy_percent": float(goal_accuracy),
                }
            )
        return result


def recalculate_prediction_quality() -> None:
    # Aggregates are calculated on the fly; nothing to persist.
    return None


def get_user_prediction_stats(user_id: int) -> Dict[str, float]:
    refresh_leaderboard()
    with session_scope() as session:
        predictions_count = session.scalar(
            select(func.count()).select_from(Prediction).where(Prediction.user_id == user_id)
        ) or 0
        res_acc = next((row for row in read_prediction_result_accuracy() if row["user_id"] == user_id), None)
        goal_acc = next((row for row in read_prediction_goal_accuracy() if row["user_id"] == user_id), None)

        leaderboard = leaderboard_rows()
        place = 0
        points = 0
        for idx, (uid, _, pts) in enumerate(leaderboard, start=1):
            if uid == user_id:
                place = idx
                points = pts
                break
        return {
            "predictions": predictions_count,
            "result_accuracy_percent": res_acc["result_accuracy_percent"] if res_acc else 0.0,
            "goal_accuracy_percent": goal_acc["goal_accuracy_percent"] if goal_acc else 0.0,
            "place": place,
            "points": points,
        }


def refresh_leaderboard() -> None:
    with session_scope() as session:
        session.execute(text("REFRESH MATERIALIZED VIEW leaderboard"))


def _calculate_points(rules: PointsRule, real1: int, real2: int, pred1: int, pred2: int) -> int:
    if real1 == pred1 and real2 == pred2:
        return rules.exact_points
    real_sign = (real1 > real2) - (real1 < real2)
    pred_sign = (pred1 > pred2) - (pred1 < pred2)
    if (real1 - real2) == (pred1 - pred2) or real_sign == pred_sign:
        return rules.result_points
    return 0


def _goal_accuracy_percent(real1: int, real2: int, pred1: int, pred2: int) -> float:
    acc1 = _single_score_accuracy(real1, pred1)
    acc2 = _single_score_accuracy(real2, pred2)
    return (acc1 + acc2) / 2 * 100.0


def _single_score_accuracy(real: int, predicted: int) -> float:
    if real == predicted:
        return 1.0
    denominator = max(real, predicted)
    if denominator == 0:
        return 1.0
    diff = abs(real - predicted)
    accuracy = 1.0 - (diff / denominator)
    return max(0.0, accuracy)


def _ensure_user(session: Session, user_id: int, username: str) -> None:
    user = session.get(User, user_id)
    if not user:
        session.add(User(id=user_id, username=username))
    elif username and user.username != username:
        user.username = username


def _match_to_dict(match: Match) -> Dict:
    return {
        "id": match.id,
        "team1": match.team1,
        "team2": match.team2,
        "score1": match.score1,
        "score2": match.score2,
        "status": match.status,
        "started_at": match.started_at,
    }


def _prediction_to_dict(pred: Prediction) -> Dict:
    return {
        "match_id": pred.match_id,
        "user_id": pred.user_id,
        "username": getattr(pred.user, "username", None),
        "pred_score1": pred.pred_score1,
        "pred_score2": pred.pred_score2,
        "timestamp": pred.created_at.isoformat(),
    }

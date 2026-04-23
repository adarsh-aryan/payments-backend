from __future__ import annotations

from typing import Tuple

from .models import OverallStatus, PaymentStatus, SettlementStatus


def derive_status(
    has_initiated: bool,
    has_processed: bool,
    has_failed: bool,
    has_settled: bool,
) -> Tuple[PaymentStatus, SettlementStatus, OverallStatus, bool]:
    """
    Returns (payment_status, settlement_status, overall_status, is_discrepant)

    Discrepancy rules implemented:
    - settled present AND failed present => inconsistent
    - processed present AND NOT settled => pending_settlement (not flagged as discrepancy here)
    - processed or initiated with settled => overall settled
    - failed without settled => overall failed
    - initiated only => initiated
    - both processed and failed present without settled => mark inconsistent
    """
    payment = PaymentStatus.unknown
    if has_failed:
        payment = PaymentStatus.failed
    elif has_processed:
        payment = PaymentStatus.processed
    elif has_initiated:
        payment = PaymentStatus.initiated
    else:
        payment = PaymentStatus.unknown

    settlement = SettlementStatus.settled if has_settled else SettlementStatus.pending

    inconsistent = False
    if has_settled and has_failed:
        inconsistent = True
    if has_processed and has_failed and not has_settled:
        inconsistent = True

    overall = OverallStatus.initiated
    if settlement == SettlementStatus.settled:
        overall = OverallStatus.settled
    else:
        if payment == PaymentStatus.failed:
            overall = OverallStatus.failed
        elif payment == PaymentStatus.processed:
            overall = OverallStatus.pending_settlement
        elif payment == PaymentStatus.initiated or payment == PaymentStatus.unknown:
            overall = OverallStatus.initiated

    if inconsistent:
        overall = OverallStatus.inconsistent

    return payment, settlement, overall, inconsistent

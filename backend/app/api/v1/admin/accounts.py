import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.v1.admin.deps import CAN_EDIT, CurrentAdmin, require_csrf
from app.core.rate_limit import rate_limit
from app.models import AccountCharge, AccountPayment, AdminUser, ClientAccount
from app.schemas.accounts import (
    AccountChargeIn,
    AccountChargeOut,
    AccountChargePatch,
    AccountPaymentIn,
    AccountPaymentOut,
    ClientAccountDetail,
    ClientAccountIn,
    ClientAccountOut,
    ClientAccountPatch,
    LinkBookingIn,
)
from app.services.accounts import balance, charge_booking

router = APIRouter(
    prefix="/admin/accounts", tags=["admin-accounts"], dependencies=[Depends(rate_limit(60))]
)
NOT_FOUND = "Account not found."


@router.get("")
async def list_accounts(_admin: CurrentAdmin, session: DbSession) -> list[ClientAccountOut]:
    rows = (await session.scalars(select(ClientAccount).order_by(ClientAccount.name))).all()
    return [ClientAccountOut.model_validate(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def create_account(
    body: ClientAccountIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> ClientAccountOut:
    account = ClientAccount(**body.model_dump())
    session.add(account)
    await session.commit()
    return ClientAccountOut.model_validate(account)


async def admin_account(
    account_id: uuid.UUID, _admin: CurrentAdmin, session: DbSession
) -> ClientAccount:
    account = await session.get(ClientAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return account


AdminAccount = Annotated[ClientAccount, Depends(admin_account)]


async def _to_detail(session: DbSession, account: ClientAccount) -> ClientAccountDetail:
    charges = await session.scalars(
        select(AccountCharge)
        .where(AccountCharge.account_id == account.id)
        .order_by(AccountCharge.created_at)
    )
    payments = await session.scalars(
        select(AccountPayment)
        .where(AccountPayment.account_id == account.id)
        .order_by(AccountPayment.received_at)
    )
    return ClientAccountDetail(
        id=account.id,
        customer_id=account.customer_id,
        name=account.name,
        status=account.status,
        credit_limit_cents=account.credit_limit_cents,
        balance_cents=await balance(session, account.id),
        charges=[AccountChargeOut.model_validate(charge) for charge in charges],
        payments=[AccountPaymentOut.model_validate(payment) for payment in payments],
    )


@router.get("/{account_id}")
async def detail_route(account: AdminAccount, session: DbSession) -> ClientAccountDetail:
    return await _to_detail(session, account)


@router.patch("/{account_id}", dependencies=[Depends(require_csrf)])
async def patch_account(
    account: AdminAccount,
    body: ClientAccountPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> ClientAccountDetail:
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    await session.commit()
    return await _to_detail(session, account)


@router.post(
    "/{account_id}/charges",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_charge(
    account: AdminAccount,
    body: AccountChargeIn,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> AccountChargeOut:
    charge = AccountCharge(
        account_id=account.id, description=body.description, amount_cents=body.amount_cents
    )
    session.add(charge)
    await session.commit()
    return AccountChargeOut.model_validate(charge)


@router.patch("/{account_id}/charges/{charge_id}", dependencies=[Depends(require_csrf)])
async def patch_charge(
    account: AdminAccount,
    charge_id: uuid.UUID,
    body: AccountChargePatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> AccountChargeOut:
    charge = await session.get(AccountCharge, charge_id)
    if charge is None or charge.account_id != account.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charge not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(charge, key, value)
    await session.commit()
    return AccountChargeOut.model_validate(charge)


@router.post(
    "/{account_id}/payments",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_payment(
    account: AdminAccount,
    body: AccountPaymentIn,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> AccountPaymentOut:
    payment = AccountPayment(
        account_id=account.id, received_by_admin_id=admin.id, **body.model_dump()
    )
    session.add(payment)
    await session.commit()
    return AccountPaymentOut.model_validate(payment)


@router.post(
    "/{account_id}/bookings",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def link_booking(
    account: AdminAccount,
    body: LinkBookingIn,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> AccountChargeOut:
    """Factura una reserva ya existente a la cuenta, sin tocar su estado (F6.8)."""
    charge = await charge_booking(session, account, body.booking_id)
    await session.commit()
    return AccountChargeOut.model_validate(charge)

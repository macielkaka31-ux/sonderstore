from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import requests
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Resend / email config
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ORDER_EMAIL_TO = os.environ.get("ORDER_EMAIL_TO", "kawemacielbrito4@gmail.com")
RESEND_FROM = os.environ.get("RESEND_FROM", "SONDER <onboarding@resend.dev>")

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# ---- Models ----
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StatusCheckCreate(BaseModel):
    client_name: str


class OrderItem(BaseModel):
    id: str
    slug: str
    name: str
    size: str
    color: Optional[str] = ""
    qty: int
    price: float
    image: Optional[str] = None


class OrderCustomer(BaseModel):
    fullName: str
    email: EmailStr
    phone: str
    address: str
    addressNumber: Optional[str] = ""
    postalCode: str
    city: str
    country: str


class OrderCreate(BaseModel):
    customer: OrderCustomer
    items: List[OrderItem]
    subtotal: float


class OrderResponse(BaseModel):
    orderId: str
    createdAt: datetime
    emailSent: bool


# ---- Helpers ----
def build_order_html(order_id: str, customer: OrderCustomer, items: List[OrderItem], subtotal: float) -> str:
    items_rows = ""
    for it in items:
        line_total = it.price * it.qty
        color_cell = it.color or "—"
        items_rows += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;'>{it.name}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center;'>{color_cell}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center;'>{it.size}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:center;'>{it.qty}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;'>€{it.price:.2f}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;text-align:right;'>€{line_total:.2f}</td>"
            f"</tr>"
        )

    address_line = customer.address
    if customer.addressNumber:
        address_line += f", {customer.addressNumber}"

    html = f"""
    <div style="font-family:'Courier New',monospace;background:#000;color:#fff;padding:24px;max-width:640px;margin:0 auto;">
      <h1 style="letter-spacing:6px;font-size:22px;margin:0 0 4px;">SONDER&reg;</h1>
      <p style="opacity:.7;font-size:11px;letter-spacing:3px;margin:0 0 24px;">NOVO PEDIDO &middot; {order_id}</p>

      <div style="background:#111;padding:16px;margin-bottom:16px;">
        <h2 style="font-size:12px;letter-spacing:3px;margin:0 0 12px;opacity:.7;">CLIENTE</h2>
        <p style="margin:4px 0;font-size:13px;"><b>Nome:</b> {customer.fullName}</p>
        <p style="margin:4px 0;font-size:13px;"><b>Email:</b> {customer.email}</p>
        <p style="margin:4px 0;font-size:13px;"><b>Telefone:</b> {customer.phone}</p>
      </div>

      <div style="background:#111;padding:16px;margin-bottom:16px;">
        <h2 style="font-size:12px;letter-spacing:3px;margin:0 0 12px;opacity:.7;">ENDEREÇO DE ENTREGA</h2>
        <p style="margin:4px 0;font-size:13px;">{address_line}</p>
        <p style="margin:4px 0;font-size:13px;">{customer.postalCode} &middot; {customer.city} &middot; {customer.country}</p>
      </div>

      <div style="background:#fff;color:#000;padding:16px;">
        <h2 style="font-size:12px;letter-spacing:3px;margin:0 0 12px;">ITENS DO PEDIDO</h2>
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
          <thead>
            <tr style="background:#f5f5f5;">
              <th style="padding:8px;text-align:left;">PRODUTO</th>
              <th style="padding:8px;text-align:center;">COR</th>
              <th style="padding:8px;text-align:center;">TAM</th>
              <th style="padding:8px;text-align:center;">QTD</th>
              <th style="padding:8px;text-align:right;">PREÇO</th>
              <th style="padding:8px;text-align:right;">TOTAL</th>
            </tr>
          </thead>
          <tbody>
            {items_rows}
          </tbody>
          <tfoot>
            <tr>
              <td colspan="5" style="padding:12px 8px;text-align:right;font-weight:bold;">TOTAL</td>
              <td style="padding:12px 8px;text-align:right;font-weight:bold;">€{subtotal:.2f}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p style="font-size:10px;letter-spacing:2px;opacity:.5;margin-top:24px;text-align:center;">
        SONDER&reg; &middot; PEDIDO RECEBIDO EM {datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")}
      </p>
    </div>
    """
    return html


def send_order_email(order_id: str, customer: OrderCustomer, items: List[OrderItem], subtotal: float) -> bool:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured; skipping email send.")
        return False

    html = build_order_html(order_id, customer, items, subtotal)
    subject = f"[SONDER®] Novo pedido {order_id} — {customer.fullName}"

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM,
                "to": [ORDER_EMAIL_TO],
                "reply_to": customer.email,
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201, 202):
            logger.info(f"Order email sent for {order_id}: {resp.status_code}")
            return True
        logger.error(f"Resend error {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        return False


# ---- Routes ----
@api_router.get("/")
async def root():
    return {"message": "Hello World"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]


@api_router.post("/orders", response_model=OrderResponse)
async def create_order(payload: OrderCreate):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Pedido sem itens.")

    order_id = "SND-" + uuid.uuid4().hex[:6].upper()
    created_at = datetime.utcnow()

    # Save to MongoDB
    record = {
        "orderId": order_id,
        "createdAt": created_at,
        "customer": payload.customer.dict(),
        "items": [it.dict() for it in payload.items],
        "subtotal": payload.subtotal,
    }
    try:
        await db.orders.insert_one(record)
    except Exception as e:
        logger.error(f"Mongo insert error: {e}")

    # Send email via Resend
    email_sent = send_order_email(order_id, payload.customer, payload.items, payload.subtotal)

    # Update record with email status
    try:
        await db.orders.update_one({"orderId": order_id}, {"$set": {"emailSent": email_sent}})
    except Exception:
        pass

    return OrderResponse(orderId=order_id, createdAt=created_at, emailSent=email_sent)


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

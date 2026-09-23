"""Seed the demo database and knowledge base (idempotent).

    python -m scripts.seed              # seed whatever is missing
    python -m scripts.seed --reset      # wipe commerce data and documents, then reseed

All data is synthetic and generated with a fixed random seed. Dates are
relative to the day the seed runs, so "last month" questions always have data.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import delete, func, insert, select, text

from app.core.config import BACKEND_DIR, get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import dispose_engines, get_session_factory, session_scope
from app.embeddings.factory import get_embedding_provider
from app.models import (
    Category,
    Customer,
    Document,
    Inventory,
    Order,
    OrderItem,
    Payment,
    Product,
    Return,
    Review,
    User,
)
from app.rag.ingestion import IngestionService
from scripts.build_documents import build_all

logger = logging.getLogger("seed")

DHAKA = timezone(timedelta(hours=6))
HISTORY_DAYS = 540
N_CUSTOMERS = 300
N_ORDERS = 950

TIER_THRESHOLDS = [(200_000, "Platinum"), (75_000, "Gold"), (25_000, "Silver"), (0, "Bronze")]

# name: (description, price range BDT, warranty months, brands, product types)
CATALOG: dict[str, tuple[str, tuple[int, int], int, list[str], list[str]]] = {
    "Electronics": (
        "Laptops, TVs, audio, cameras and accessories.",
        (1_500, 140_000),
        12,
        ["Samsung", "Sony", "Walton", "Xiaomi", "HP", "Lenovo", "Asus", "JBL", "Anker", "Logitech"],
        [
            "Laptop 14in",
            "Smart TV 43in",
            "Bluetooth Speaker",
            "Wireless Earbuds",
            "Monitor 24in",
            "Power Bank 20000mAh",
            "Mechanical Keyboard",
            "Webcam 1080p",
            "Smartwatch",
            "Action Camera",
        ],
    ),
    "Mobile Phones": (
        "Smartphones and feature phones.",
        (6_000, 160_000),
        12,
        ["Samsung", "Xiaomi", "Realme", "Oppo", "Vivo", "Apple", "Symphony", "Walton", "Tecno"],
        [
            "Galaxy A",
            "Redmi Note",
            "Narzo",
            "Reno",
            "Y Series",
            "iPhone",
            "Z Series",
            "Primo",
            "Spark",
            "Camon",
        ],
    ),
    "Home Appliances": (
        "Refrigerators, ACs, washing machines and kitchen appliances.",
        (1_800, 120_000),
        24,
        ["Walton", "Samsung", "LG", "Singer", "Vision", "Panasonic", "Sharp", "Miyako"],
        [
            "Refrigerator 380L",
            "Split AC 1.5 Ton",
            "Washing Machine 8kg",
            "Microwave Oven 25L",
            "Blender 3-in-1",
            "Ceiling Fan",
            "Rice Cooker 1.8L",
            "Air Fryer 4L",
            "Water Purifier",
            "Electric Kettle",
        ],
    ),
    "Fashion": (
        "Clothing, footwear and accessories.",
        (450, 7_500),
        0,
        ["Aarong", "Yellow", "Richman", "Ecstasy", "Bata", "Apex", "Sailor", "Infinity"],
        [
            "Cotton Panjabi",
            "Silk Saree",
            "Denim Jeans",
            "Formal Shirt",
            "Leather Sandals",
            "Sneakers",
            "Three-Piece Set",
            "Polo T-Shirt",
            "Winter Jacket",
            "Leather Wallet",
        ],
    ),
    "Books": (
        "Fiction, non-fiction and academic books in Bengali and English.",
        (180, 2_200),
        0,
        ["Prothoma", "Anyaprokash", "Penguin", "Oxford", "Somoy", "Ananya"],
        [
            "Novel",
            "Poetry Collection",
            "Programming Guide",
            "History of Bengal",
            "Business Strategy",
            "Children's Stories",
            "Cookbook",
            "Self-Help",
            "Science Encyclopedia",
            "Exam Preparation",
        ],
    ),
    "Beauty & Personal Care": (
        "Skincare, cosmetics, grooming and fragrances.",
        (150, 4_500),
        0,
        ["Nivea", "Lakme", "Garnier", "Ponds", "Dove", "Philips", "Himalaya", "Loreal"],
        [
            "Face Wash",
            "Moisturizer",
            "Sunscreen SPF50",
            "Hair Dryer",
            "Beard Trimmer",
            "Lipstick",
            "Perfume 100ml",
            "Shampoo 400ml",
            "Body Lotion",
            "Serum 30ml",
        ],
    ),
    "Groceries": (
        "Rice, oil, spices, snacks and daily essentials.",
        (80, 2_400),
        0,
        ["Pran", "ACI", "Teer", "Fresh", "Radhuni", "Ispahani", "Chashi", "Bashundhara"],
        [
            "Miniket Rice 5kg",
            "Soybean Oil 5L",
            "Red Lentils 2kg",
            "Tea 400g",
            "Spice Mix",
            "Aromatic Rice 2kg",
            "Sugar 1kg",
            "Instant Noodles Pack",
            "Ghee 500g",
            "Honey 500g",
        ],
    ),
    "Sports & Outdoors": (
        "Fitness, cricket, football and outdoor gear.",
        (400, 65_000),
        3,
        ["Yonex", "Adidas", "Nike", "Decathlon", "SG", "Cosco", "Duranta", "Veloce"],
        [
            "Cricket Bat",
            "Football",
            "Badminton Racket",
            "Treadmill",
            "Yoga Mat",
            "Dumbbell Set",
            "Mountain Bicycle",
            "Tent 4-Person",
            "Running Shoes",
            "Gym Gloves",
        ],
    ),
    "Toys": (
        "Toys and games for children.",
        (250, 9_000),
        0,
        ["Lego", "Hasbro", "Mattel", "Funskool", "Chicco", "Hot Wheels"],
        [
            "Building Blocks",
            "RC Car",
            "Doll House",
            "Board Game",
            "Puzzle 500pc",
            "Plush Toy",
            "Educational Robot",
            "Toy Kitchen Set",
            "Kids Scooter",
            "Drawing Kit",
        ],
    ),
    "Furniture": (
        "Home and office furniture.",
        (2_500, 85_000),
        6,
        ["Hatil", "Otobi", "Regal", "Navana", "Brothers", "Akhtar"],
        [
            "Sofa 3-Seater",
            "Office Chair",
            "Dining Table 6-Seat",
            "Wardrobe",
            "Study Desk",
            "Bookshelf",
            "Queen Bed",
            "TV Cabinet",
            "Shoe Rack",
            "Recliner",
        ],
    ),
}

FIRST_NAMES_M = [
    "Rahim",
    "Karim",
    "Tanvir",
    "Arif",
    "Sakib",
    "Nayeem",
    "Fahim",
    "Imran",
    "Rakib",
    "Hasan",
    "Mehedi",
    "Shuvo",
    "Sabbir",
    "Rashed",
    "Zahid",
    "Anik",
    "Tamim",
    "Ayan",
]
FIRST_NAMES_F = [
    "Rahima",
    "Nusrat",
    "Farzana",
    "Sadia",
    "Tahmina",
    "Ayesha",
    "Mim",
    "Jannat",
    "Sumaiya",
    "Tasnim",
    "Nabila",
    "Riya",
    "Shirin",
    "Lamia",
    "Anika",
    "Fatema",
]
LAST_NAMES = [
    "Akter",
    "Hossain",
    "Rahman",
    "Islam",
    "Ahmed",
    "Chowdhury",
    "Khan",
    "Uddin",
    "Sarker",
    "Das",
    "Roy",
    "Miah",
    "Begum",
    "Talukder",
    "Siddique",
    "Karim",
    "Paul",
]
BD_CITIES = [
    ("Dhaka", 40),
    ("Chattogram", 14),
    ("Sylhet", 7),
    ("Rajshahi", 6),
    ("Khulna", 6),
    ("Gazipur", 6),
    ("Narayanganj", 5),
    ("Cumilla", 4),
    ("Barishal", 4),
    ("Rangpur", 4),
    ("Mymensingh", 4),
]
FOREIGN = [
    ("India", "Kolkata"),
    ("United Arab Emirates", "Dubai"),
    ("United Kingdom", "London"),
    ("United States", "New York"),
    ("Malaysia", "Kuala Lumpur"),
]
WAREHOUSES = ["Dhaka Central", "Chattogram Hub", "Sylhet Depot"]
RETURN_REASONS = {
    "default": [
        ("defective", 30),
        ("damaged_in_transit", 15),
        ("wrong_item", 10),
        ("not_as_described", 20),
        ("changed_mind", 25),
    ],
    "Fashion": [
        ("size_issue", 45),
        ("not_as_described", 20),
        ("changed_mind", 25),
        ("wrong_item", 10),
    ],
}
RETURN_RATE = {
    "Electronics": 0.14,
    "Mobile Phones": 0.12,
    "Home Appliances": 0.10,
    "Fashion": 0.18,
    "Furniture": 0.08,
    "Toys": 0.07,
    "Groceries": 0.02,
}
REVIEW_TEXT = {
    5: [
        ("Excellent product", "Works perfectly and delivery was fast."),
        ("খুবই ভালো", "পণ্যের মান চমৎকার, সময়মতো ডেলিভারি পেয়েছি।"),
        ("Highly recommended", "Great value for money."),
    ],
    4: [("Very good", "Good quality, packaging could be better."), ("ভালো পণ্য", "দাম অনুযায়ী মান ভালো।")],
    3: [("Average", "It is okay for the price."), ("Decent", "Does the job but nothing special.")],
    2: [
        ("Disappointed", "Quality is lower than expected."),
        ("Not great", "Stopped working properly after a few weeks."),
    ],
    1: [
        ("Very poor", "Arrived damaged and support was slow."),
        ("খারাপ অভিজ্ঞতা", "পণ্যটি বর্ণনার সাথে মেলেনি।"),
    ],
}


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def weighted(rng: random.Random, options: list[tuple[Any, int]]) -> Any:
    values, weights = zip(*options, strict=True)
    return rng.choices(values, weights=weights, k=1)[0]


@dataclass
class Generated:
    categories: list[dict]
    products: list[dict]
    customers: list[dict]
    orders: list[dict]
    items: list[dict]
    payments: list[dict]
    inventory: list[dict]
    returns: list[dict]
    reviews: list[dict]


def generate(now: datetime, seed: int = 42) -> Generated:
    rng = random.Random(seed)
    categories, products = [], []
    product_category: dict[int, str] = {}
    popularity: list[float] = []
    for cat_id, (name, (desc, (low, high), warranty, brands, types)) in enumerate(
        CATALOG.items(), 1
    ):
        categories.append({"id": cat_id, "name": name, "description": desc})
        for index in range(22):
            pid = len(products) + 1
            brand = brands[index % len(brands)]
            kind = types[(index * 3 + cat_id) % len(types)]
            # Log-uniform: many affordable items, few premium ones (like a real catalogue).
            raw_price = math.exp(rng.uniform(math.log(low), math.log(high)))
            price = money(max(low, round(raw_price / 10) * 10 - 1))
            products.append(
                {
                    "id": pid,
                    "sku": f"NX-{cat_id:02d}-{pid:04d}",
                    "name": f"{brand} {kind} {chr(65 + index % 26)}{rng.randint(10, 99)}",
                    "category_id": cat_id,
                    "brand": brand,
                    "price": price,
                    "cost_price": money(float(price) * rng.uniform(0.62, 0.82)),
                    "warranty_months": warranty,
                    "is_active": rng.random() > 0.05,
                    "launched_at": (now - timedelta(days=rng.randint(HISTORY_DAYS, 900))).date(),
                }
            )
            product_category[pid] = name
            # Cheaper items sell far more often than premium ones.
            popularity.append(rng.paretovariate(1.3) * (1_000 / float(price)) ** 0.6)

    customers = []
    customer_weights = []
    used_emails: set[str] = set()
    for cid in range(1, N_CUSTOMERS + 1):
        gender = rng.choice(["male", "female"])
        first = rng.choice(FIRST_NAMES_M if gender == "male" else FIRST_NAMES_F)
        last = rng.choice(LAST_NAMES)
        email = f"{first}.{last}{cid}@example.com".lower()
        used_emails.add(email)
        if rng.random() < 0.88:
            country, city = "Bangladesh", weighted(rng, BD_CITIES)
        else:
            country, city = rng.choice(FOREIGN)
        customers.append(
            {
                "id": cid,
                "full_name": f"{first} {last}",
                "email": email,
                "phone": f"+8801{rng.randint(3, 9)}{rng.randint(10_000_000, 99_999_999)}",
                "gender": gender,
                "city": city,
                "country": country,
                "membership_tier": "Bronze",
            }
        )
        customer_weights.append(rng.paretovariate(1.2))

    orders, items, payments, returns, reviews = [], [], [], [], []
    first_order: dict[int, datetime] = {}
    for oid in range(1, N_ORDERS + 1):
        days_ago = rng.triangular(0, HISTORY_DAYS, 0)
        placed = (now - timedelta(days=days_ago)).replace(
            hour=rng.randint(8, 23), minute=rng.randint(0, 59), second=0, microsecond=0
        )
        placed = min(placed, now - timedelta(minutes=5))
        customer = rng.choices(customers, weights=customer_weights, k=1)[0]
        first_order[customer["id"]] = min(first_order.get(customer["id"], placed), placed)
        domestic = customer["country"] == "Bangladesh"
        age = (now - placed).days
        if age > 10:
            status = weighted(rng, [("delivered", 92), ("cancelled", 8)])
        elif age > 3:
            status = weighted(
                rng, [("delivered", 60), ("shipped", 30), ("processing", 5), ("cancelled", 5)]
            )
        else:
            status = weighted(
                rng, [("pending", 40), ("processing", 40), ("shipped", 15), ("cancelled", 5)]
            )

        chosen = rng.choices(
            range(len(products)), weights=popularity, k=rng.choice([1, 1, 2, 2, 3, 4])
        )
        subtotal = Decimal("0")
        order_items = []
        for product_index in dict.fromkeys(chosen):
            product = products[product_index]
            qty = (
                rng.randint(1, 5)
                if product_category[product["id"]] == "Groceries"
                else rng.choice([1, 1, 1, 2, 3])
            )
            unit = product["price"]
            discount = (
                money(float(unit) * qty * rng.choice([0.05, 0.1, 0.15]))
                if rng.random() < 0.12
                else money(0)
            )
            line = money(unit * qty - discount)
            subtotal += line
            item = {
                "id": len(items) + 1,
                "order_id": oid,
                "product_id": product["id"],
                "quantity": qty,
                "unit_price": unit,
                "discount_amount": discount,
                "line_total": line,
            }
            items.append(item)
            order_items.append(item)

        if not domestic:
            shipping = money(1500)
        elif subtotal >= 3000:
            shipping = money(0)
        else:
            shipping = money(60 if customer["city"] == "Dhaka" else 120)
        order_discount = money(float(subtotal) * 0.05) if rng.random() < 0.08 else money(0)
        total = money(subtotal - order_discount + shipping)
        orders.append(
            {
                "id": oid,
                "order_number": f"NX-{placed.year}-{oid:06d}",
                "customer_id": customer["id"],
                "order_date": placed,
                "status": status,
                "channel": weighted(rng, [("web", 45), ("mobile_app", 45), ("store", 10)]),
                "shipping_city": customer["city"],
                "shipping_country": customer["country"],
                "subtotal": money(subtotal),
                "discount_amount": order_discount,
                "shipping_fee": shipping,
                "total_amount": total,
                "currency": "BDT",
            }
        )

        # Payments
        if domestic:
            method = weighted(
                rng,
                [
                    ("bkash", 35),
                    ("nagad", 15),
                    ("card", 20),
                    ("cash_on_delivery", 25),
                    ("bank_transfer", 5),
                ],
            )
            if method == "cash_on_delivery" and total > 20_000:
                method = "card"
        else:
            method = weighted(rng, [("card", 90), ("bank_transfer", 10)])
        if method != "cash_on_delivery" and rng.random() < 0.05:
            payments.append(
                {
                    "id": len(payments) + 1,
                    "order_id": oid,
                    "amount": total,
                    "method": method,
                    "status": "failed",
                    "paid_at": None,
                    "transaction_ref": f"TX{rng.randint(10**9, 10**10 - 1)}",
                }
            )
        if status == "cancelled":
            pay_status, paid_at = (
                ("failed", None)
                if method == "cash_on_delivery"
                else ("refunded", placed + timedelta(minutes=2))
            )
        elif status == "delivered":
            pay_status = "completed"
            paid_at = placed + (
                timedelta(days=rng.randint(1, 4))
                if method == "cash_on_delivery"
                else timedelta(minutes=2)
            )
        elif method == "cash_on_delivery":
            pay_status, paid_at = "pending", None
        else:
            pay_status, paid_at = "completed", placed + timedelta(minutes=2)
        payments.append(
            {
                "id": len(payments) + 1,
                "order_id": oid,
                "amount": total,
                "method": method,
                "status": pay_status,
                "paid_at": paid_at,
                "transaction_ref": f"TX{rng.randint(10**9, 10**10 - 1)}",
            }
        )

        if status != "delivered":
            continue
        delivered_at = placed + timedelta(days=rng.randint(1, 4))
        for item in order_items:
            category = product_category[item["product_id"]]
            if rng.random() < RETURN_RATE.get(category, 0.05):
                requested = delivered_at + timedelta(
                    days=rng.randint(1, 20), hours=rng.randint(0, 12)
                )
                if requested >= now:
                    continue
                reason = weighted(rng, RETURN_REASONS.get(category, RETURN_REASONS["default"]))
                if (now - requested).days < 4:
                    ret_status, resolved = "requested", None
                else:
                    ret_status = weighted(
                        rng, [("refunded", 65), ("approved", 20), ("rejected", 15)]
                    )
                    resolved = min(requested + timedelta(days=rng.randint(2, 6)), now)
                refund = item["line_total"] if ret_status == "refunded" else money(0)
                returns.append(
                    {
                        "id": len(returns) + 1,
                        "order_item_id": item["id"],
                        "order_id": oid,
                        "product_id": item["product_id"],
                        "customer_id": customer["id"],
                        "quantity": item["quantity"],
                        "reason": reason,
                        "status": ret_status,
                        "refund_amount": refund,
                        "requested_at": requested,
                        "resolved_at": resolved,
                    }
                )
            elif rng.random() < 0.33:
                rating = weighted(rng, [(5, 45), (4, 30), (3, 12), (2, 7), (1, 6)])
                title, body = rng.choice(REVIEW_TEXT[rating])
                created = delivered_at + timedelta(days=rng.randint(1, 15))
                if created < now:
                    reviews.append(
                        {
                            "id": len(reviews) + 1,
                            "product_id": item["product_id"],
                            "customer_id": customer["id"],
                            "rating": rating,
                            "title": title,
                            "body": body,
                            "created_at": created,
                        }
                    )

    # Membership tier = rolling 12-month spend on non-cancelled orders (see membership policy).
    spend: dict[int, Decimal] = defaultdict(Decimal)
    refunds_by_order: dict[int, Decimal] = defaultdict(Decimal)
    for r in returns:
        refunds_by_order[r["order_id"]] += r["refund_amount"]
    for order in orders:
        if order["status"] != "cancelled" and order["order_date"] >= now - timedelta(days=365):
            spend[order["customer_id"]] += order["total_amount"] - refunds_by_order[order["id"]]
    for customer in customers:
        total = spend[customer["id"]]
        customer["membership_tier"] = next(
            tier for limit, tier in TIER_THRESHOLDS if total >= limit
        )
        signup_anchor = first_order.get(customer["id"], now - timedelta(days=rng.randint(5, 200)))
        customer["created_at"] = signup_anchor - timedelta(
            days=rng.randint(1, 90), hours=rng.randint(0, 23)
        )

    inventory = []
    for product in products:
        for warehouse in WAREHOUSES:
            if warehouse != "Dhaka Central" and rng.random() < 0.35:
                continue
            on_hand = (
                0
                if rng.random() < 0.06
                else rng.randint(3, 320 if warehouse == "Dhaka Central" else 120)
            )
            inventory.append(
                {
                    "id": len(inventory) + 1,
                    "product_id": product["id"],
                    "warehouse": warehouse,
                    "quantity_on_hand": on_hand,
                    "reserved_quantity": min(on_hand, rng.randint(0, 8)),
                    "reorder_level": rng.choice([10, 15, 20, 25, 30, 40]),
                    "updated_at": now - timedelta(hours=rng.randint(1, 240)),
                }
            )

    return Generated(
        categories, products, customers, orders, items, payments, inventory, returns, reviews
    )


async def seed_admin() -> None:
    settings = get_settings()
    async with session_scope() as session:
        existing = await session.scalar(
            select(User).where(User.email == settings.admin_email.lower())
        )
        if existing is None:
            session.add(
                User(
                    email=settings.admin_email.lower(),
                    full_name="Administrator",
                    password_hash=hash_password(settings.admin_password.get_secret_value()),
                    role="admin",
                )
            )
            logger.info("Created admin user %s", settings.admin_email)


async def seed_commerce(reset: bool) -> None:
    tables = [Review, Return, Payment, OrderItem, Order, Inventory, Customer, Product, Category]
    async with session_scope() as session:
        if reset:
            for model in tables:
                await session.execute(delete(model))
        elif await session.scalar(select(func.count(Category.id))):
            logger.info("Commerce data already present; skipping")
            return
        data = generate(datetime.now(DHAKA))
        for model, rows in [
            (Category, data.categories),
            (Product, data.products),
            (Customer, data.customers),
            (Order, data.orders),
            (OrderItem, data.items),
            (Payment, data.payments),
            (Inventory, data.inventory),
            (Return, data.returns),
            (Review, data.reviews),
        ]:
            for start in range(0, len(rows), 1000):
                await session.execute(insert(model), rows[start : start + 1000])
            # Table names come from our own ORM metadata, never from user input.
            table = model.__table__.fullname
            sequence_sql = (
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "  # noqa: S608
                f"(SELECT MAX(id) FROM {table}))"
            )
            await session.execute(text(sequence_sql))
        logger.info(
            "Seeded %d customers, %d products, %d orders, %d items, %d returns, %d reviews",
            len(data.customers),
            len(data.products),
            len(data.orders),
            len(data.items),
            len(data.returns),
            len(data.reviews),
        )
    async with session_scope() as session:
        await session.execute(text("ANALYZE"))


async def seed_documents(reset: bool) -> None:
    settings = get_settings()
    service = IngestionService(get_session_factory(), get_embedding_provider(), settings)
    async with session_scope() as session:
        if reset:
            for document in (await session.scalars(select(Document))).all():
                await session.delete(document)
        elif await session.scalar(select(func.count(Document.id))):
            logger.info("Knowledge base already present; skipping")
            return
    for path in build_all(BACKEND_DIR / "storage" / "seed_documents"):
        document = await service.create_document(
            data=path.read_bytes(),
            filename=path.name,
            content_type=None,
            title=path.stem.replace("_", " "),
            uploaded_by=None,
        )
        await service.process_document(document.id)
        logger.info("Indexed %s", path.name)


async def main(reset: bool, skip_documents: bool) -> None:
    configure_logging(get_settings().log_level)
    try:
        await seed_admin()
        await seed_commerce(reset)
        if not skip_documents:
            await seed_documents(reset)
    finally:
        await dispose_engines()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="wipe and regenerate demo data")
    parser.add_argument("--skip-documents", action="store_true", help="only seed the database")
    args = parser.parse_args()
    asyncio.run(main(args.reset, args.skip_documents))

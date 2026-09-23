"""Business tables (`commerce` schema) queried by the Text-to-SQL engine.

The `comment=` strings are the single source of truth for schema descriptions:
migrations turn them into PostgreSQL COMMENTs and the schema inspector reads
them back to explain the database to the language model. To describe a new
column, add a comment here and generate a migration.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SCHEMA = "commerce"
Money = Numeric(12, 2)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        {"schema": SCHEMA, "comment": "Product categories (e.g. Electronics, Books)."},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, comment="Category display name.")
    description: Mapped[str | None] = mapped_column(Text, comment="Short category description.")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_id", "category_id"),
        {"schema": SCHEMA, "comment": "Catalog of products sold by the company."},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, comment="Stock keeping unit code.")
    name: Mapped[str] = mapped_column(String(200), comment="Product name.")
    category_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.categories.id"), comment="Category of the product."
    )
    brand: Mapped[str] = mapped_column(String(100), comment="Brand / manufacturer.")
    price: Mapped[Decimal] = mapped_column(Money, comment="Current list price in BDT.")
    cost_price: Mapped[Decimal] = mapped_column(Money, comment="Unit purchase cost in BDT.")
    warranty_months: Mapped[int] = mapped_column(
        SmallInteger, default=0, comment="Manufacturer warranty length in months (0 = none)."
    )
    is_active: Mapped[bool] = mapped_column(default=True, comment="False if discontinued.")
    launched_at: Mapped[date] = mapped_column(Date, comment="Date the product was first listed.")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_country", "country"),
        Index("ix_customers_membership_tier", "membership_tier"),
        {"schema": SCHEMA, "comment": "Customers who have an account with the store."},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), comment="Customer full name.")
    email: Mapped[str] = mapped_column(String(320), unique=True, comment="Customer email.")
    phone: Mapped[str | None] = mapped_column(String(30), comment="Contact phone number.")
    gender: Mapped[str | None] = mapped_column(String(10), comment="'male' or 'female'.")
    city: Mapped[str] = mapped_column(String(100), comment="City of residence, e.g. 'Dhaka'.")
    country: Mapped[str] = mapped_column(
        String(100), comment="Country of residence, e.g. 'Bangladesh', 'India'."
    )
    membership_tier: Mapped[str] = mapped_column(
        String(20),
        comment="Loyalty tier: 'Bronze', 'Silver', 'Gold' or 'Platinum' "
        "(benefits are defined in the Customer Membership Policy document).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Account sign-up time."
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_order_date", "order_date"),
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
        {
            "schema": SCHEMA,
            "comment": "Customer orders. Revenue = SUM(total_amount) of orders whose status "
            "is not 'cancelled'.",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(
        String(30), unique=True, comment="Human-readable order number, e.g. 'NX-2026-000123'."
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.customers.id"), comment="Customer who placed the order."
    )
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="When the order was placed."
    )
    status: Mapped[str] = mapped_column(
        String(20),
        comment="One of 'pending', 'processing', 'shipped', 'delivered', 'cancelled'.",
    )
    channel: Mapped[str] = mapped_column(
        String(20), comment="Sales channel: 'web', 'mobile_app' or 'store'."
    )
    shipping_city: Mapped[str] = mapped_column(String(100), comment="Delivery city.")
    shipping_country: Mapped[str] = mapped_column(String(100), comment="Delivery country.")
    subtotal: Mapped[Decimal] = mapped_column(Money, comment="Sum of line totals in BDT.")
    discount_amount: Mapped[Decimal] = mapped_column(
        Money, default=0, comment="Order-level discount in BDT."
    )
    shipping_fee: Mapped[Decimal] = mapped_column(Money, default=0, comment="Shipping fee in BDT.")
    total_amount: Mapped[Decimal] = mapped_column(
        Money, comment="Amount charged: subtotal - discount_amount + shipping_fee (BDT)."
    )
    currency: Mapped[str] = mapped_column(String(3), default="BDT", comment="Always 'BDT'.")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        {
            "schema": SCHEMA,
            "comment": "Line items of each order. Units sold = SUM(quantity); product revenue "
            "= SUM(line_total).",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.orders.id", ondelete="CASCADE"), comment="Parent order."
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.products.id"), comment="Product purchased."
    )
    quantity: Mapped[int] = mapped_column(Integer, comment="Units purchased.")
    unit_price: Mapped[Decimal] = mapped_column(Money, comment="Price per unit at purchase (BDT).")
    discount_amount: Mapped[Decimal] = mapped_column(
        Money, default=0, comment="Line discount in BDT."
    )
    line_total: Mapped[Decimal] = mapped_column(
        Money, comment="quantity * unit_price - discount_amount (BDT)."
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_order_id", "order_id"),
        {"schema": SCHEMA, "comment": "Payment transactions for orders."},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.orders.id", ondelete="CASCADE"), comment="Order being paid."
    )
    amount: Mapped[Decimal] = mapped_column(Money, comment="Payment amount in BDT.")
    method: Mapped[str] = mapped_column(
        String(30),
        comment="'bkash', 'nagad', 'card', 'cash_on_delivery' or 'bank_transfer'.",
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="'completed', 'pending', 'failed' or 'refunded'."
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="When the payment settled (NULL if not settled)."
    )
    transaction_ref: Mapped[str] = mapped_column(String(60), comment="Gateway reference.")


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse", name="uq_inventory_product_warehouse"),
        {
            "schema": SCHEMA,
            "comment": "Current stock per product per warehouse. Total stock of a product = "
            "SUM(quantity_on_hand) across warehouses.",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.products.id"), comment="Stocked product."
    )
    warehouse: Mapped[str] = mapped_column(
        String(60), comment="'Dhaka Central', 'Chattogram Hub' or 'Sylhet Depot'."
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, comment="Units physically in stock.")
    reserved_quantity: Mapped[int] = mapped_column(
        Integer, default=0, comment="Units reserved for open orders."
    )
    reorder_level: Mapped[int] = mapped_column(
        Integer, comment="Restock when quantity_on_hand falls below this level."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="Last stock update."
    )


class Return(Base):
    __tablename__ = "returns"
    __table_args__ = (
        Index("ix_returns_product_id", "product_id"),
        Index("ix_returns_requested_at", "requested_at"),
        {
            "schema": SCHEMA,
            "comment": "Product return requests. A refund happened when status = 'refunded'; "
            "refund_amount is the money given back.",
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.order_items.id", ondelete="CASCADE"), comment="Returned line item."
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.orders.id", ondelete="CASCADE"), comment="Order of the item."
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.products.id"), comment="Returned product."
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.customers.id"), comment="Customer who returned it."
    )
    quantity: Mapped[int] = mapped_column(Integer, comment="Units returned.")
    reason: Mapped[str] = mapped_column(
        String(40),
        comment="'defective', 'damaged_in_transit', 'wrong_item', 'not_as_described', "
        "'size_issue' or 'changed_mind'.",
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="'requested', 'approved', 'rejected' or 'refunded'."
    )
    refund_amount: Mapped[Decimal] = mapped_column(
        Money, default=0, comment="Amount refunded in BDT (0 unless refunded)."
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="When the return was requested."
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="When the return was approved/rejected/refunded."
    )


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_product_id", "product_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        {"schema": SCHEMA, "comment": "Product reviews written by customers."},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.products.id"), comment="Reviewed product."
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.customers.id"), comment="Review author."
    )
    rating: Mapped[int] = mapped_column(SmallInteger, comment="Star rating from 1 to 5.")
    title: Mapped[str] = mapped_column(String(200), comment="Review headline.")
    body: Mapped[str] = mapped_column(Text, comment="Review text.")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="When the review was posted."
    )

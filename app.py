import os
import psycopg2
import psycopg2.extras
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM customers ORDER BY name")
    customers = cur.fetchall()

    cur.execute("""
        SELECT 
            c.id,
            c.name,
            c.phone,
            c.credit_limit,
            COALESCE(SUM(t.amount), 0) AS balance
        FROM customers c
        LEFT JOIN transactions t ON c.id = t.customer_id
        GROUP BY c.id, c.name, c.phone, c.credit_limit
        ORDER BY c.name
    """)
    balances = cur.fetchall()

    cur.execute("""
        SELECT t.*, c.name AS customer_name
        FROM transactions t
        LEFT JOIN customers c ON c.id = t.customer_id
        ORDER BY t.id DESC
        LIMIT 30
    """)
    transactions = cur.fetchall()

    cur.execute("SELECT * FROM accessories ORDER BY name")
    accessories = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        customers=customers,
        balances=balances,
        transactions=transactions,
        accessories=accessories
    )


@app.route("/add_customer", methods=["POST"])
def add_customer():
    name = request.form.get("name")
    phone = request.form.get("phone")
    credit_limit = request.form.get("credit_limit") or 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO customers (name, phone, credit_limit)
        VALUES (%s, %s, %s)
    """, (name, phone, credit_limit))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index"))


@app.route("/charge", methods=["POST"])
def charge():
    customer_id = request.form.get("customer_id")
    trans_type = request.form.get("type")
    item = request.form.get("item")
    amount = float(request.form.get("amount") or 0)
    car_reg = request.form.get("car_reg")

    if trans_type == "Payment":
        amount = -abs(amount)
    else:
        amount = abs(amount)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (customer_id, type, item, amount, car_reg, date)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        customer_id,
        trans_type,
        item,
        amount,
        car_reg,
        datetime.now()
    ))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index"))


@app.route("/add_accessory", methods=["POST"])
def add_accessory():
    name = request.form.get("name")
    qty = request.form.get("qty") or 0
    price = request.form.get("price") or 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO accessories (name, qty, price)
        VALUES (%s, %s, %s)
    """, (name, qty, price))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)

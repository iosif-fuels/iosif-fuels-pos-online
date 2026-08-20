import os
from datetime import datetime, date

import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)

app.secret_key = "iosif_pos_secret_123"
POS_PASSWORD = "1122"

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT current_batch FROM settings WHERE id = 1")
    batch = cur.fetchone()[0]
    cur.execute("SELECT * FROM customers ORDER BY name")
    customers = cur.fetchall()

    cur.execute("SELECT * FROM accessories ORDER BY name")
    accessories = cur.fetchall()

    cur.execute("""
        SELECT t.*, c.name AS customer_name
        FROM transactions t
        LEFT JOIN customers c ON c.id = t.customer_id
        ORDER BY t.id DESC
        LIMIT 10
    """)
    transactions = cur.fetchall()

    cur.execute("""
        SELECT c.id, c.name, c.phone, c.credit_limit,
               COALESCE(SUM(t.amount), 0) AS balance
        FROM customers c
        LEFT JOIN transactions t ON c.id = t.customer_id
        GROUP BY c.id, c.name, c.phone, c.credit_limit
        ORDER BY c.name
    """)
    balances = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        customers=customers,
        accessories=accessories,
        transactions=transactions,
        balances=balances,
        batch=batch
    )


@app.route("/_customer", methods=["POST"])
def _customer():
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


    customer_name = customer[0] if customer else ""

    cur.execute("""
        INSERT INTO receipts (transaction_id, receipt_type, customer_name, item, amount, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        transaction_id,
        trans_type,
        customer_name,
        item,
        amount,
        datetime.now()
    ))

    receipt_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("receipt_pdf", receipt_id=receipt_id))

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
    """, (customer_id, trans_type, item, amount, car_reg, datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index"))


@app.route("/add_accessory", methods=["POST"])
def add_accessory():
    name = request.form.get("name")
    qty = request.form.get("qty") or 0
    buy_price = request.form.get("buy_price") or 0
    sell_price = request.form.get("sell_price") or 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO accessories (name, qty, buy_price, sell_price, price)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, qty, buy_price, sell_price, sell_price))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index"))


@app.route("/sell_accessory", methods=["POST"])
def sell_accessory():
    accessory_id = request.form.get("accessory_id")
    qty_sold = int(request.form.get("qty") or 1)

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM accessories WHERE id = %s", (accessory_id,))
    accessory = cur.fetchone()

    if not accessory:
        cur.close()
        conn.close()
        return "Accessory not found"

    if accessory["qty"] < qty_sold:
        cur.close()
        conn.close()
        return "Not enough stock"

    total = float(accessory["sell_price"] or accessory["price"]) * qty_sold
    item_text = accessory["name"] + " x " + str(qty_sold)

    cur.execute("""
        INSERT INTO transactions (customer_id, type, item, amount, car_reg, date)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        None,
        "Accessories",
        item_text,
        total,
        "Cash Sale",
        datetime.now()
    ))

    transaction_id = cur.fetchone()[0]

    cur.execute("""
        INSERT INTO receipts (transaction_id, receipt_type, customer_name, item, amount, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        transaction_id,
        "Accessory Sale",
        "Cash Sale",
        item_text,
        total,
        datetime.now()
    ))

    receipt_id = cur.fetchone()[0]

    cur.execute("""
        UPDATE accessories
        SET qty = qty - %s
        WHERE id = %s
    """, (qty_sold, accessory_id))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("receipt_pdf", receipt_id=receipt_id))

@app.route("/reports")
def reports():
    today = request.args.get("report_date") or str(date.today())

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT type, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE DATE(date) = %s
        GROUP BY type
    """, (today,))
    daily_by_type = cur.fetchall()

    cur.execute("""
        SELECT t.*, c.name AS customer_name
        FROM transactions t
        LEFT JOIN customers c ON c.id = t.customer_id
        WHERE DATE(t.date) = %s
        ORDER BY t.id DESC
    """, (today,))
    daily_transactions = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND amount > 0
    """, (today,))
    daily_sales = cur.fetchone()["total"]

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND amount < 0
    """, (today,))
    daily_payments = abs(cur.fetchone()["total"])

    cur.execute("""
        SELECT *
        FROM daily_closings
        ORDER BY day DESC
    """)
    closed_days = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "reports.html",
        today=today,
        daily_by_type=daily_by_type,
        daily_transactions=daily_transactions,
        daily_sales=daily_sales,
        daily_payments=daily_payments,
        closed_days=closed_days,
        selected_date=today
    )


@app.route("/end_day", methods=["POST"])
def end_day():
    today = date.today()

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND type = 'Accessories'
    """, (today,))
    accessories_sales = cur.fetchone()["total"]

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND customer_id IS NOT NULL AND amount > 0
    """, (today,))
    customer_charges = cur.fetchone()["total"]

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND customer_id IS NOT NULL AND amount < 0
    """, (today,))
    customer_payments = abs(cur.fetchone()["total"])

    total_sales = accessories_sales + customer_charges

    cur.execute("""
        INSERT INTO daily_closings
        (day, accessories_sales, customer_charges, customer_payments, total_sales, closed_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (day)
        DO UPDATE SET
            accessories_sales = EXCLUDED.accessories_sales,
            customer_charges = EXCLUDED.customer_charges,
            customer_payments = EXCLUDED.customer_payments,
            total_sales = EXCLUDED.total_sales,
            closed_at = EXCLUDED.closed_at
    """, (
        today,
        accessories_sales,
        customer_charges,
        customer_payments,
        total_sales,
        datetime.now()
    ))
    cur.execute("""
        UPDATE settings
        SET current_batch = current_batch + 1
        WHERE id = 1
    """)
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("reports"))
@app.route("/monthly_report")
def monthly_report():
    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT type, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE TO_CHAR(date, 'YYYY-MM') = %s
        GROUP BY type
        ORDER BY type
    """, (selected_month,))
    monthly_by_type = cur.fetchall()

    cur.execute("""
        SELECT item, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE TO_CHAR(date, 'YYYY-MM') = %s
        AND type = 'Accessories'
        GROUP BY item
        ORDER BY total DESC
    """, (selected_month,))
    monthly_accessories = cur.fetchall()

    cur.execute("""
        SELECT c.id, c.name,
               COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 0) AS charges,
               COALESCE(SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END), 0) AS payments,
               COALESCE(SUM(t.amount), 0) AS balance_change
        FROM customers c
        LEFT JOIN transactions t
            ON c.id = t.customer_id
            AND TO_CHAR(t.date, 'YYYY-MM') = %s
        GROUP BY c.id, c.name
        ORDER BY c.name
    """, (selected_month,))
    customer_monthly = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "monthly_report.html",
        selected_month=selected_month,
        monthly_by_type=monthly_by_type,
        monthly_accessories=monthly_accessories,
        customer_monthly=customer_monthly
    )


@app.route("/customers")
def customers():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT c.id, c.name, c.phone, c.credit_limit,
               COALESCE(SUM(t.amount), 0) AS balance
        FROM customers c
        LEFT JOIN transactions t ON c.id = t.customer_id
        GROUP BY c.id, c.name, c.phone, c.credit_limit
        ORDER BY c.name
    """)
    customers = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("customers.html", customers=customers)


@app.route("/customer_statement/<int:customer_id>")
def customer_statement(customer_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
    customer = cur.fetchone()

    cur.execute("""
        SELECT *
        FROM transactions
        WHERE customer_id = %s
        ORDER BY date DESC
    """, (customer_id,))
    transactions = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS balance
        FROM transactions
        WHERE customer_id = %s
    """, (customer_id,))
    balance = cur.fetchone()["balance"]

    cur.close()
    conn.close()

    return render_template(
        "customer_statement.html",
        customer=customer,
        transactions=transactions,
        balance=balance
    )
@app.route("/daily_report_pdf")
def daily_report_pdf():
    selected_date = request.args.get("report_date")

    if selected_date:
        today = selected_date
    else:
        today = date.today()

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT t.*, c.name AS customer_name
        FROM transactions t
        LEFT JOIN customers c ON c.id = t.customer_id
        WHERE DATE(t.date) = %s
        ORDER BY t.id DESC
    """, (today,))
    transactions = cur.fetchall()

    cur.execute("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND amount > 0
    """, (today,))
    daily_sales = cur.fetchone()["total"]

    cur.execute("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM transactions
        WHERE DATE(date) = %s AND amount < 0
    """, (today,))
    daily_payments = abs(cur.fetchone()["total"])

    cur.close()
    conn.close()

    from io import BytesIO
    from flask import send_file
    from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("IOSIF FUELS DAILY REPORT", styles["Title"]))
    elements.append(Paragraph(str(today), styles["Heading2"]))
    elements.append(Spacer(1, 20))

    elements.append(Paragraph(f"Sales: EUR {daily_sales}", styles["Normal"]))
    elements.append(Paragraph(f"Payments: EUR {daily_payments}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    data = [["Date", "Customer", "Type", "Item", "Amount"]]

    for t in transactions:
        data.append([
            str(t["date"]),
            t["customer_name"] or "Cash",
            t["type"],
            t["item"],
            str(t["amount"])
        ])

    table = Table(data)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name="daily_report.pdf",
        mimetype="application/pdf"
    )

@app.route("/monthly_report_pdf")
def monthly_report_pdf():
    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT *
        FROM transactions
        WHERE TO_CHAR(date, 'YYYY-MM') = %s
        ORDER BY date DESC
    """, (selected_month,))
    transactions = cur.fetchall()

    cur.close()
    conn.close()

    from io import BytesIO
    from flask import send_file
    from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("IOSIF FUELS MONTHLY REPORT", styles["Title"]))
    elements.append(Paragraph(selected_month, styles["Heading2"]))
    elements.append(Spacer(1, 20))

    data = [["Date", "Type", "Item", "Amount"]]

    for t in transactions:
        data.append([
            str(t["date"]),
            t["type"],
            t["item"],
            str(t["amount"])
        ])

    table = Table(data)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name="monthly_report.pdf",
        mimetype="application/pdf"
    )

@app.route("/customer_statement_pdf/<int:customer_id>")
def customer_statement_pdf(customer_id):

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Get customer
    cur.execute("""
        SELECT *
        FROM customers
        WHERE id = %s
    """, (customer_id,))

    customer = cur.fetchone()

    # Get customer transactions
    cur.execute("""
        SELECT *
        FROM transactions
        WHERE customer_id = %s
        ORDER BY date DESC
    """, (customer_id,))

    transactions = cur.fetchall()

    # Calculate balance
    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS balance
        FROM transactions
        WHERE customer_id = %s
    """, (customer_id,))

    balance = cur.fetchone()["balance"]

    cur.close()
    conn.close()


    # PDF IMPORTS
    from io import BytesIO
    from flask import send_file

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.units import mm

    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer
    )


    # CREATE PDF
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()


    # CUSTOM STYLES

    title_style = ParagraphStyle(
        "StatementTitle",
        parent=styles["Title"],
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#172238"),
        spaceAfter=6
    )


    company_style = ParagraphStyle(
        "Company",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#667085"),
        spaceAfter=15
    )


    customer_label_style = ParagraphStyle(
        "CustomerLabel",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#667085")
    )


    customer_value_style = ParagraphStyle(
        "CustomerValue",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#172238")
    )


    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        textColor=colors.white
    )


    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#344054"),
        wordWrap="CJK"
    )


    amount_style = ParagraphStyle(
        "Amount",
        parent=table_cell_style,
        alignment=TA_RIGHT
    )


    # PDF ELEMENTS

    elements = []


    # TITLE

    elements.append(
        Paragraph(
            "CUSTOMER STATEMENT",
            title_style
        )
    )

    elements.append(
        Paragraph(
            "IOSIF P IOSIF TRADING LTD",
            company_style
        )
    )


    # CUSTOMER INFORMATION

    customer_info = [
        [
            Paragraph("CUSTOMER", customer_label_style),
            Paragraph("PHONE", customer_label_style),
            Paragraph("CURRENT BALANCE", customer_label_style)
        ],

        [
            Paragraph(
                str(customer["name"] or "-"),
                customer_value_style
            ),

            Paragraph(
                str(customer["phone"] or "-"),
                customer_value_style
            ),

            Paragraph(
                f"EUR {float(balance or 0):,.2f}",
                customer_value_style
            )
        ]
    ]


    info_table = Table(
        customer_info,
        colWidths=[
            70 * mm,
            50 * mm,
            50 * mm
        ]
    )


    info_table.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F6F9")),

        ("BOX", (0, 0), (-1, -1),
         0.5,
         colors.HexColor("#D0D5DD")),

        ("INNERGRID", (0, 0), (-1, -1),
         0.5,
         colors.HexColor("#D0D5DD")),

        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        ("TOPPADDING", (0, 0), (-1, -1), 8),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),

        ("LEFTPADDING", (0, 0), (-1, -1), 8),

        ("RIGHTPADDING", (0, 0), (-1, -1), 8)

    ]))


    elements.append(info_table)

    elements.append(Spacer(1, 18))


    # TRANSACTION TITLE

    elements.append(
        Paragraph(
            "TRANSACTION HISTORY",
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 8))


    # TRANSACTION TABLE

    data = [

        [
            Paragraph("DATE", table_header_style),

            Paragraph("TYPE", table_header_style),

            Paragraph("DESCRIPTION", table_header_style),

            Paragraph(
                "AMOUNT",
                ParagraphStyle(
                    "AmountHeader",
                    parent=table_header_style,
                    alignment=TA_RIGHT
                )
            )
        ]

    ]


    # ADD TRANSACTIONS

    for t in transactions:

        transaction_date = str(t["date"] or "")

        transaction_type = str(t["type"] or "-")

        transaction_item = str(t["item"] or "-")

        transaction_amount = float(t["amount"] or 0)


        # Payment = negative display
        if transaction_type.lower() == "payment":

            amount_text = f"- EUR {abs(transaction_amount):,.2f}"

        else:

            amount_text = f"+ EUR {abs(transaction_amount):,.2f}"


        data.append([

            Paragraph(
                transaction_date,
                table_cell_style
            ),

            Paragraph(
                transaction_type,
                table_cell_style
            ),

            Paragraph(
                transaction_item,
                table_cell_style
            ),

            Paragraph(
                amount_text,
                amount_style
            )

        ])


    # If no transactions

    if len(data) == 1:

        data.append([

            Paragraph(
                "No transactions found",
                table_cell_style
            ),

            "",

            "",

            ""

        ])


    # CREATE TABLE

    transaction_table = Table(

        data,

        repeatRows=1,

        colWidths=[

            42 * mm,   # Date

            28 * mm,   # Type

            82 * mm,   # Description

            38 * mm    # Amount

        ]

    )


    transaction_table.setStyle(TableStyle([

        # HEADER

        ("BACKGROUND",
         (0, 0),
         (-1, 0),
         colors.HexColor("#172238")),

        ("TEXTCOLOR",
         (0, 0),
         (-1, 0),
         colors.white),


        # GRID

        ("GRID",
         (0, 0),
         (-1, -1),
         0.4,
         colors.HexColor("#D0D5DD")),


        # ALIGNMENT

        ("VALIGN",
         (0, 0),
         (-1, -1),
         "MIDDLE"),


        # PADDING

        ("TOPPADDING",
         (0, 0),
         (-1, -1),
         7),

        ("BOTTOMPADDING",
         (0, 0),
         (-1, -1),
         7),

        ("LEFTPADDING",
         (0, 0),
         (-1, -1),
         6),

        ("RIGHTPADDING",
         (0, 0),
         (-1, -1),
         6),


        # AMOUNT ALIGNMENT

        ("ALIGN",
         (3, 1),
         (3, -1),
         "RIGHT"),

        # BODY BACKGROUND

        ("BACKGROUND",
         (0, 1),
         (-1, -1),
         colors.white)

    ]))


    elements.append(transaction_table)

    elements.append(Spacer(1, 20))


    # FOOTER

    elements.append(
        Paragraph(
            "IOSIF P IOSIF TRADING LTD | Customer Account Statement",
            ParagraphStyle(
                "Footer",
                parent=styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor("#98A2B3"),
                alignment=TA_LEFT
            )
        )
    )


    # BUILD PDF

    doc.build(elements)

    buffer.seek(0)


    return send_file(

        buffer,

        as_attachment=False,

        download_name=f"{customer['name']}_statement.pdf",

        mimetype="application/pdf"

    )
@app.route("/accessories_statement")
def accessories_statement():
    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT *
        FROM accessories
        ORDER BY name
    """)
    accessories = cur.fetchall()

    cur.execute("""
        SELECT 
            item,
            SUM(amount) AS total_sales
        FROM transactions
        WHERE type = 'Accessories'
        AND TO_CHAR(date, 'YYYY-MM') = %s
        GROUP BY item
        ORDER BY total_sales DESC
    """, (selected_month,))
    accessory_sales = cur.fetchall()

    cur.execute("""
        SELECT 
            COALESCE(SUM(t.amount), 0) AS total_sell,
            COALESCE(SUM(a.buy_price), 0) AS total_buy
        FROM transactions t
        LEFT JOIN accessories a
            ON t.item LIKE a.name || '%%'
        WHERE t.type = 'Accessories'
        AND TO_CHAR(t.date, 'YYYY-MM') = %s
    """, (selected_month,))
    monthly_totals = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "accessories_statement.html",
        accessories=accessories,
        accessory_sales=accessory_sales,
        selected_month=selected_month,
        monthly_totals=monthly_totals
    )

@app.route("/fuel_stock")
def fuel_stock():
    fuel_types = [
        "Unleaded 95",
        "Unleaded 98",
        "Eurodiesel",
        "Heating Diesel",
        "Kerosene",
        "Agriculture Diesel"
    ]

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    current_stock = []

    for fuel in fuel_types:
        cur.execute("""
            SELECT COALESCE(SUM(
                CASE 
                    WHEN movement_type IN ('Opening Stock', 'Delivery') THEN liters
                    WHEN movement_type = 'Sold' THEN -liters
                    ELSE 0
                END
            ), 0) AS liters
            FROM fuel_movements
            WHERE fuel_type = %s
        """, (fuel,))
        liters = cur.fetchone()["liters"]

        current_stock.append({
            "fuel_type": fuel,
            "liters": liters
        })

    cur.execute("""
        SELECT *
        FROM fuel_movements
        ORDER BY created_at DESC
        LIMIT 50
    """)
    movements = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "fuel_stock.html",
        fuel_types=fuel_types,
        current_stock=current_stock,
        movements=movements
    )


@app.route("/add_fuel_movement", methods=["POST"])
def add_fuel_movement():
    fuel_type = request.form.get("fuel_type")
    movement_type = request.form.get("movement_type")
    liters = float(request.form.get("liters") or 0)
    note = request.form.get("note")

    conn = get_db()
    cur = conn.cursor()

    # If morning tank reading, reset today's real tank level
    if movement_type == "Tank Reading":

        # Delete previous tank reading for this fuel today
        cur.execute("""
            DELETE FROM fuel_movements
            WHERE fuel_type = %s
            AND movement_type = 'Tank Reading'
            AND DATE(created_at) = CURRENT_DATE
        """, (fuel_type,))

        cur.execute("""
            INSERT INTO fuel_movements (
                fuel_type,
                movement_type,
                liters,
                note,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            fuel_type,
            movement_type,
            liters,
            note,
            datetime.now()
        ))

    else:
        # Delivery or Sold
        cur.execute("""
            INSERT INTO fuel_movements (
                fuel_type,
                movement_type,
                liters,
                note,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            fuel_type,
            movement_type,
            liters,
            note,
            datetime.now()
        ))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("fuel_stock"))

@app.route("/add_customer", methods=["POST"])
def add_customer():
    name = request.form.get("name")
    phone = request.form.get("phone")
    credit_limit = request.form.get("credit_limit") or 0
    opening_balance = float(request.form.get("opening_balance") or 0)

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO customers (name, phone, credit_limit)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (name, phone, credit_limit))

    customer_id = cur.fetchone()[0]

    if opening_balance > 0:
        cur.execute("""
            INSERT INTO transactions (customer_id, type, item, amount, car_reg, date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            customer_id,
            "Opening Balance",
            "Previous Balance",
            opening_balance,
            "Opening Account",
            datetime.now()
        ))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("manager"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")

        if password == POS_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))

        return render_template("login.html", error="Wrong password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.before_request
def require_login():
    allowed_routes = ["login", "static"]

    if request.endpoint in allowed_routes:
        return

    if not session.get("logged_in"):
        return redirect(url_for("login"))
@app.route("/delete_customer/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM transactions WHERE customer_id = %s", (customer_id,))
    cur.execute("DELETE FROM customers WHERE id = %s", (customer_id,))

    conn.commit()
    cur.close()
    conn.close()

    flash("Customer deleted successfully")
    return redirect(url_for("customers"))
@app.route("/receipt_pdf/<int:receipt_id>")
def receipt_pdf(receipt_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM receipts WHERE id = %s", (receipt_id,))
    receipt = cur.fetchone()

    cur.close()
    conn.close()

    if not receipt:
        return "Receipt not found"

    from io import BytesIO
    from flask import send_file
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    vat_rate = 0.19
    total = float(receipt["amount"])
    net = round(total / (1 + vat_rate), 2)
    vat = round(total - net, 2)

    buffer = BytesIO()

    # Thermal receipt width
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(220, 600),
        rightMargin=10,
        leftMargin=10,
        topMargin=10,
        bottomMargin=10
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("IOSIF P. IOSIF TRADING LTD", styles["Title"]))
    elements.append(Paragraph("10, Marion Street", styles["Normal"]))
    elements.append(Paragraph("TEL: 26321425", styles["Normal"]))
    elements.append(Paragraph("VAT REG. NO: 10162349G", styles["Normal"]))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("--------------------------------------", styles["Normal"]))
    elements.append(Paragraph("PRODUCT   PRICE   QTY   VALUE", styles["Normal"]))
    elements.append(
        Paragraph(
            f"{receipt['item']}   {receipt['amount']}   1   {receipt['amount']}",
            styles["Normal"]
        )
    )
    elements.append(Paragraph("--------------------------------------", styles["Normal"]))

    elements.append(
        Paragraph(f"TOTAL (€): {receipt['amount']}", styles["Heading2"])
    )

    elements.append(Paragraph("--------------------------------------", styles["Normal"]))
    elements.append(Paragraph("RATE   CODE   NET   VAT   TOTAL", styles["Normal"]))
    elements.append(
        Paragraph(
            f"19%    A    {net}   {vat}   {total}",
            styles["Normal"]
        )
    )

    elements.append(Paragraph("--------------------------------------", styles["Normal"]))
    elements.append(
        Paragraph(f"DATE: {receipt['created_at']}", styles["Normal"])
    )
    elements.append(Paragraph("CASHIER: IOSIF", styles["Normal"]))
    elements.append(
        Paragraph(f"RECEIPT NO: {receipt['id']}", styles["Normal"])
    )

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f"receipt_{receipt_id}.pdf",
        mimetype="application/pdf"
    )

@app.route("/void_transaction/<int:transaction_id>", methods=["POST"])
def void_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE transactions
        SET voided = TRUE
        WHERE id = %s
    """, (transaction_id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("index"))
@app.route("/manager")
def manager():
    return render_template("manager.html")

@app.route("/edit_customer/<int:customer_id>", methods=["GET", "POST"])
def edit_customer(customer_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        credit_limit = request.form.get("credit_limit") or 0

        cur.execute("""
            UPDATE customers
            SET name = %s, phone = %s, credit_limit = %s
            WHERE id = %s
        """, (name, phone, credit_limit, customer_id))

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("customers"))

    cur.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
    customer = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("edit_customer.html", customer=customer)

@app.route("/products")
def products():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT *
        FROM accessories
        ORDER BY name
    """)
    products = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("products.html", products=products)
@app.route("/transactions")
def transactions_page():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT t.*, c.name AS customer_name
        FROM transactions t
        LEFT JOIN customers c ON c.id = t.customer_id
        WHERE COALESCE(t. voided, FALSE) = FALSE
        ORDER BY t.id DESC
        LIMIT 100
    """)
    transactions = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("transactions.html", transactions=transactions)
if __name__ == "__main__":
    app.run(debug=True)
    
    

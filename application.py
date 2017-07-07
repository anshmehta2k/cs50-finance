from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
import os

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    stocks = db.execute("SELECT * FROM curs JOIN users ON curs.user_id = users.id JOIN stocks ON curs.stock_id = stocks.id WHERE users.id = :id AND shares != 0",
        id = session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :id",
        id = session["user_id"])
    
    fin = float(cash[0]["cash"])
    
    if len(stocks) == 0:
        return render_template("indexempty.html", cash = fin, fin = fin)
    
    for stock in stocks:
        q = lookup(stock["symbol"])
        if stock["price"] != q["price"]:
            db.execute("UPDATE stocks SET price = :price WHERE symbol = :symbol",
                price = q["price"], symbol = stock["symbol"])
        fin += float(stock["shares"]) * float(stock["price"])
    
    
    return render_template("index.html", cash = cash[0]["cash"], stocks = stocks, fin = fin)
    

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("please enter symbol")
        if not request.form.get("shares"):
            return apology("please enter number of shares")
        sy = request.form.get("symbol").upper()
        sh = request.form.get("shares")
        q = lookup(sy)
        if q == None:
            return apology("Invalid symbol")
        cash = db.execute("SELECT cash FROM users WHERE id = :id",
            id = session["user_id"])
        if float(sh) *  float(q["price"]) > cash[0]["cash"]:
            return apology("Not enough cash")
        if len(db.execute("SELECT * FROM stocks WHERE symbol = :symbol", 
            symbol = sy)) != 1:
                db.execute("INSERT INTO stocks (name, symbol, price) VALUES (:name, :symbol, :price)",
                    name = q["name"], symbol = sy, price = q["price"])
        stock = db.execute("SELECT * FROM stocks WHERE symbol = :symbol",
            symbol = sy)[0]
        if stock["price"] != q["price"]:
                db.execute("UPDATE stocks SET price = :price WHERE symbol = :symbol",
                    price = q["price"], symbol = sy)
        db.execute("INSERT INTO transactions (user_id, stock_id, shares, cost) VALUES (:user_id, :stock_id, :shares, :cost)",
            user_id = session["user_id"], stock_id = stock["id"], shares = float(sh), cost = float(sh) * float(q["price"]) )
        db.execute("UPDATE users SET cash = cash - :cost WHERE id = :id",
            cost = float(sh) * float(q["price"]), id = session["user_id"] )
        if len(db.execute("SELECT * FROM curs WHERE stock_id = :sid AND user_id = :id ",
            sid = stock["id"], id = session["user_id"])) == 0:
                db.execute("INSERT INTO curs (user_id, stock_id, shares) VALUES (:u, :s, :sh)",
                    u = session["user_id"], s = stock["id"], sh = float(sh))
        else:
            db.execute("UPDATE curs SET shares = shares + :sh WHERE user_id = :id AND stock_id = :sid",
                id = session["user_id"], sid  = stock["id"], sh = float(sh))
        return redirect(url_for("index"))
    else:
        return render_template("buy.html")
    return apology("TODO")

@app.route("/history")
@login_required
def history():
    ts = db.execute("SELECT * FROM transactions JOIN stocks ON transactions.stock_id = stocks.id WHERE user_id = :uid", uid = session["user_id"])
    if len(ts) == 0:
        return apology("no transactions")
    else:
        return render_template("history.html", ts = ts)
    return apology("TODO")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("please enter symbol")
        else:
            return render_template("quoted.html", quote=lookup(request.form.get("symbol")))
    else:
        return render_template("quote.html")
            
    return apology("TODO")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("please enter username")
        if not request.form.get("password"):
            return apology("please enter password")
        if not request.form.get("password") == request.form.get("password2"):
            return apology("passwords don't match")
        success = db.execute("INSERT INTO 'users' (username, hash) VALUES (:username, :hash)", username = request.form.get("username"), hash = pwd_context.hash(request.form.get("password")))
        if success == None:
            return apology("username already exists")
    else:
        return render_template("register.html")
    return apology("TODO")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Symbol required")
        if not request.form.get("shares"):
            return apology("Number of shares required")
        sy = request.form.get("symbol").upper()
        sh = request.form.get("shares")
        q = lookup(sy)
        
        if q == None:
            return apology("Invalid symbol")
        cash = db.execute("SELECT cash FROM users WHERE id = :id",
            id = session["user_id"])
        shares = db.execute("SELECT * FROM curs JOIN stocks ON curs.stock_id = stocks.id WHERE symbol = :symbol AND user_id = :id", 
            symbol = sy, id = session["user_id"])
        if len(shares) != 1:
                return apology("no stocks of this share")
        if float(sh) > shares[0]["shares"]:
            return apology("not enough shares")
        if shares[0]["price"] != q["price"]:
                db.execute("UPDATE stocks SET price = :price WHERE symbol = :symbol",
                    price = q["price"], symbol = sy)
        db.execute("INSERT INTO transactions (user_id, stock_id, shares, cost) VALUES (:user_id, :stock_id, :shares, :cost)",
            user_id = session["user_id"], stock_id = shares[0]["id"], shares = -float(sh), cost = float(sh) * float(q["price"]) )
        db.execute("UPDATE users SET cash = cash + :cost WHERE id = :id",
            cost = float(sh) * float(q["price"]), id = session["user_id"] )
        db.execute("UPDATE curs SET shares = shares - :sh WHERE user_id = :id AND stock_id = :sid",
                id = session["user_id"], sid  = shares[0]["id"], sh = float(sh))
        return redirect(url_for("index"))
    else:
        return render_template("sell.html")
    return apology("TODO")
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port = port)

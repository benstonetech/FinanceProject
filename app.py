from flask import Flask, render_template, request, session, redirect, flash, make_response, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import update
from helpers import lookup, usd, full_lookup
from models import db
from flask_session import Session
from tempfile import mkdtemp
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand
import datetime
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash


import psycopg2


app = Flask(__name__)

app.jinja_env.filters["usd"] = usd
app.add_template_global(usd, name='usd')

app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["DEBUG"] = False

app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_TYPE"] = "filesystem"

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL')
app.secret_key = os.environ.get('SECRET_KEY')


Session(app)


#db.init_app(app)
db = SQLAlchemy(app)

migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command('db', MigrateCommand)

class users(db.Model):
    id = db.Column('id', db.Integer, primary_key = True)
    username = db.Column('username',db.String(100))
    hash = db.Column('hash', db.String(255))
    cash = db.Column('cash',db.Numeric)

    def __init__(self, username, hash, cash):
        
        self.username = username
        self.hash = hash
        self.cash = cash
 
class users_stocks(db.Model):
    id = db.Column('id',db.Integer, primary_key = True)
    user_id = db.Column('user_id', db.Integer)
    stock_symbol = db.Column('stock_symbol',db.String(100))
    stock_quantity = db.Column('stock_quantity', db.Integer)
    
    def __init__(self,user_id, stock_symbol, stock_quantity):
        self.user_id = user_id
        self.stock_symbol = stock_symbol
        self.stock_quantity = stock_quantity
   
class transactions(db.Model):
    trans_id = db.Column('trans_id',db.Integer,autoincrement = True, primary_key = True)
    user_id = db.Column('user_id', db.Integer)
    symbol = db.Column('symbol',db.String(100))
    name = db.Column('name', db.String(100))
    trans_type = db.Column('trans_type', db.String(100))
    shares = db.Column('shares', db.Integer)
    price = db.Column('price', db.Numeric(precision=2))
    timestamp = db.Column('timestamp', db.DateTime)
    
    def __init__(self, user_id,symbol,name, trans_type,shares,price,timestamp):
        self.user_id = user_id
        self.symbol = symbol
        self.name = name
        self.trans_type = trans_type
        self.shares = shares
        self.price = price
        self.timestamp = timestamp





@app.route('/')
def index():
    c_username = request.cookies.get('c_username')
    c_logged_in = request.cookies.get('c_logged_in')
    c_cash = request.cookies.get('c_cash')
    c_user_id = request.cookies.get('c_user_id')

    g.c_logged_in = c_logged_in
    g.c_cash = c_cash

    if c_logged_in == 'True':
    #if session.get("logged_in") == True:
        cash = users.query.filter_by(id = c_user_id).all()
        
        users_stock = users_stocks.query.filter_by(user_id = c_user_id).all()
        current_stock_data = []
        #get current stock price
        totalStockValue = 0
        
        for x in users_stock:
            temp = lookup(x.stock_symbol)
            x.currentPrice = temp["price"]
            x.stockValue = x.currentPrice * x.stock_quantity
            totalStockValue = totalStockValue + x.stockValue
            print("stock")
        portfolioValue = float(cash[0].cash) + totalStockValue
        
        return render_template("index.html", cash=usd(cash[0].cash), users_stocks = users_stock , current_stock_data=current_stock_data, totalStockValue=usd(totalStockValue), portfolioValue=usd(portfolioValue))
    else :
        return redirect("/login")

@app.route("/logout", methods=["GET", "POST"])
def logout():
    resp = make_response(redirect("/login"))
    
    resp.set_cookie('c_user_id', expires=0)
    resp.set_cookie('c_cash', expires=0)
    resp.set_cookie('c_logged_in', expires=0)

    return resp

@app.route("/quote", methods=["GET", "POST"])
def quote():
    c_logged_in = request.cookies.get('c_logged_in')
    c_cash = request.cookies.get('c_cash')
    c_user_id = request.cookies.get('c_user_id')
    g.c_logged_in = c_logged_in
    g.c_cash = c_cash
    
    if c_logged_in == 'True':
        quoteRequested = 0
        company_data = ""
        if request.method == "POST":
            company_symbol = request.form.get("symbol")

            company_data = lookup(str(company_symbol))

            quote_requested = 1

            return render_template("quote.html",company_data=company_data, quote_requested=quote_requested)
        else:
            return render_template("quote.html")
    else:
        return redirect("/login")

@app.route("/buy", methods=["GET", "POST"])
def buy():

    c_username = request.cookies.get('c_username')
    c_logged_in = request.cookies.get('c_logged_in')
    c_cash = request.cookies.get('c_cash')
    c_user_id = request.cookies.get('c_user_id')
    g.c_logged_in = c_logged_in
    g.c_cash = c_cash
    
    if c_logged_in == 'True':
        if request.method == "POST":
            symbol = request.form.get("symbol")
            someshares = request.form.get("shares")
            if someshares != '':
                shares = int(someshares)
            else:
                shares = None

            if shares == None:
                flash("Please enter the number of shares", "danger")
                return redirect("/buy")
            elif shares == 0:
                flash("Please enter the number of shares", "danger")
                return redirect("/buy")

            else :
                company_data = lookup(symbol)
                # if company exists eg helper.py->lookup() will return none if company is not found
                if company_data == None:
                    flash("Company not found", "danger")
                    return redirect("/buy")
                else:
                    price = company_data["price"]
                    symbol = company_data["symbol"]
                    name = company_data["name"]
                    total_cost = float(price) * float(shares)

                    user_data = users.query.filter_by(id = c_user_id).all()

                    if user_data[0].cash > total_cost:
                        # Deduct the cash from the account
                        user_data[0].cash = float(user_data[0].cash) - total_cost
        #moved set cookie to end of function
                        
                        # Add the log for the transaction
                        data = transactions(
                            c_user_id,symbol,name,"BOUGHT",shares,price,datetime.datetime.now()
                        )
                        db.session.add(data)
                        db.session.commit()

                        # Add or update the portfolio
                        users_stock = users_stocks.query.filter_by(user_id = c_user_id, stock_symbol = symbol).all()
                    # print(str(users_stock[0].stock_quantity))
                        if len(users_stock) == 1:
                            print("Buying more" + str(shares)+" shares")
                            users_stock[0].stock_quantity = users_stock[0].stock_quantity + shares
                            db.session.commit()
                            print("bought")
                        if len(users_stock) == 0:
                            print("you dont yet own the stock")
                            stock = users_stocks(
                                c_user_id,symbol,shares
                            )
                            db.session.add(stock)
                            db.session.commit()
                        
                        if shares == 1:
                            flash("You successfully bought a share in " + symbol, "success")
                        else:
                            flash("You successfull bought " + str(shares) + " shares in " + symbol, "success")
                    else:
                        flash("You don't have enough money in your account","danger")
                        return redirect("/buy")

                    #Set cash cookie and return to homescreen
                    resp = make_response(redirect("/"))
                    c = float(c_cash) - total_cost
                    resp.set_cookie('c_cash',str(c))
                
                    return resp   
        else:
            return render_template("buy.html")
    else:
        return redirect("/login")

@app.route("/register", methods=["GET", "POST"])
def register():
    
    if request.method == "POST":
        # Check username doesn't already exist

        _username = request.form.get("username")
        _users = users.query.filter_by(username = _username).all()

        if len(_users) == 1 :
            user_valid = 0
        else:
            user_valid = 1

        # Check the password fields match
        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")

        if password == confirm_password:
            # Hash the password
            hashed_password = generate_password_hash(password)
            print("Hashed Password:" + hashed_password)

            pass_valid = 1
        else:
            pass_valid = 0

        # Update the database
        if user_valid == 1 and pass_valid == 1:
            # Set starting cash to $10,000
            cash = 10000
            # Create a new user and commit to the database
            new_user = users(
                    _username,hashed_password,cash
                )
            db.session.add(new_user)
            db.session.commit()

            # Retrieve the new users and set the session variables 
            the_user = users.query.filter_by(username = _username).all()


            resp = make_response(redirect("/"))
            resp.set_cookie('c_user_id',str(the_user[0].id) )
            resp.set_cookie('c_cash',str(the_user[0].cash))
            resp.set_cookie('c_logged_in','True' )

            return resp
            
        elif user_valid == 0 and pass_valid == 1:
            flash("Username is not available","danger")
            return redirect("/register")
        elif user_valid == 1 and pass_valid == 0:
            flash("Passwords do not match", "danger")
            return redirect("/register")
        elif user_valid == 0 and pass_valid == 0:
            flash("Username is not available and passwords do not match", "danger")
            return redirect("/register")

    else:
        return render_template("register.html")


@app.route("/history")
def history():
    c_logged_in = request.cookies.get('c_logged_in')
    c_cash = request.cookies.get('c_cash')
    c_user_id = request.cookies.get('c_user_id')
    g.c_logged_in = c_logged_in
    g.c_cash = c_cash

    if c_logged_in == 'True':
        _history_data = transactions.query.filter_by(user_id = c_user_id).all()
        return render_template("history.html", history_data = _history_data)
    else:
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    
    # Forget any user_id
    session.clear()

    if request.method == "POST":

        username=request.form.get("username")
        rows = users.query.filter_by(username = username).all()
        
        if len(rows) == 1:
            if check_password_hash(rows[0].hash, request.form.get("password")):
        
                # session["user_id"] = rows[0].id
                # session["cash"] = rows[0].cash
                # session["logged_in"] = True
                resp = make_response(redirect("/"))
                resp.set_cookie('c_user_id',str(rows[0].id) )
                resp.set_cookie('c_cash',str(rows[0].cash))
                resp.set_cookie('c_logged_in','True' )

                return resp
                
            else :
                flash("Invalid username or password","danger")
                print("Invalid password")
                return redirect("/login")
        else: 
            flash("Invalid username or password","danger")
            
            return redirect("/login")
           
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/sell",  methods=["GET", "POST"])
def sell():
    c_logged_in = request.cookies.get('c_logged_in')
    c_cash = request.cookies.get('c_cash')
    c_user_id = request.cookies.get('c_user_id')
    g.c_logged_in = c_logged_in
    g.c_cash = c_cash

    if c_logged_in == 'True':
        _users_stocks = users_stocks.query.filter_by(user_id = c_user_id)
        
        if request.method == "POST":
            selling_stock = request.form.get("stock")
            #number_to_sell = int(request.form.get("number_to_sell"))
            n_sell = request.form.get("number_to_sell")
            if n_sell != '':
                number_to_sell = int(n_sell)
            else:
                number_to_sell = None

            if selling_stock == None:
                flash("Please select a stock to sell", "danger")
                return redirect("/sell")
            
            elif number_to_sell == None:
                flash("Please enter the number you would like to sell", "danger")
                return redirect("/sell")
            else:
                stock_owned = 0
                user_stock_to_sell = users_stocks.query.filter_by(user_id = c_user_id).filter_by(stock_symbol = selling_stock )
                
                print(user_stock_to_sell[0].stock_quantity)

                stock_quote = lookup(selling_stock)
                stock_price = stock_quote["price"]

                total_sale_price = stock_price * float(number_to_sell)

                if user_stock_to_sell[0].stock_quantity < number_to_sell:
                    
                    flash("You don't have that many to sell","danger")

                    return redirect("/sell")
                else:
                    ## Add to transactions
                    data = transactions(
                        c_user_id,stock_quote["symbol"],stock_quote["name"],"SOLD",number_to_sell,stock_price,datetime.datetime.now()
                    )
                    db.session.add(data)
                    
                #   Change cash
                    user_data = users.query.filter_by(id = c_user_id)
                    user_data[0].cash = float(user_data[0].cash) + total_sale_price
                    c_cash = float(c_cash) + total_sale_price
                    g.c_cash = float(g.c_cash) + total_sale_price

                    if user_stock_to_sell[0].stock_quantity > number_to_sell:
                        user_stock_to_sell[0].stock_quantity = user_stock_to_sell[0].stock_quantity - number_to_sell
                    
                    elif user_stock_to_sell[0].stock_quantity == number_to_sell:
                        user_stock_to_sell.delete()

                    db.session.commit()
                    flash("Stock sold successfully","success")

                    #set the cookie
                    resp = make_response(redirect("/"))
                    resp.set_cookie('c_cash', str(c_cash))

                    return resp
                
        return render_template("sell.html", users_stocks=_users_stocks)
        
    else:
        return redirect("/login")

@app.errorhandler(404)
def page_not_found(e):
    
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run()
    manager.run()
    db.create_all()
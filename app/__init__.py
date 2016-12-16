from flask import Flask
from flask.ext.cache import Cache  
from flask.ext.sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config.from_object('config')
app.cache = Cache(app)
db = SQLAlchemy(app)

from app import views, models

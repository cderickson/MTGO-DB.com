from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_login import LoginManager

# Initialize Flask extensions
db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager() 
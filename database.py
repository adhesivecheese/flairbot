from sqlalchemy import Column, String, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
engine = create_engine(f"sqlite:///flairbot.db")

class Flairs(Base):
	__tablename__ = 'flairs'

	flair_key   = Column(String(100), primary_key=True)
	created_utc = Column(Integer)
	post_id     = Column(String(20), nullable=True)
	flair_text  = Column(String(100))
	flair_class = Column(String(100), nullable=True)
	sub_requirement = Column(String(20))
	age_requirement = Column(Integer)
	recurring       = Column(Integer)

class Themes(Base):
	__tablename__ = 'themes'

	flair_key   = Column(String(100), primary_key=True)
	created_utc = Column(Integer)
	post_id     = Column(String(20))
	theme_tag   = Column(String(100))
	flair_text  = Column(String(100))
	flair_class = Column(String(100), nullable=True)
	sub_requirement = Column(String(20))

class EventsTeam(Base):
	__tablename__ = "eventsteam"

	username = Column(String(20), primary_key=True)
	currently_authorized = Column(Integer)

Base.metadata.create_all(engine)
connection = engine.connect()
Session = sessionmaker(bind=engine)
session = Session()
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, distinct, case

app = Flask(__name__)

# Database Configuration (Replace with your Toolforge database details)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://user:password@localhost/database'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define Database Models (can also be in models.py)
class Campaign(db.Model):
    __tablename__ = 'campaigns'
    campaign_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer)
    description = db.Column(db.Text)
    editathons = db.relationship('Editathon', backref='campaign', lazy=True)

class Editathon(db.Model):
    __tablename__ = 'editathons'
    editathon_id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.campaign_id'), nullable=False)
    sitename = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    description = db.Column(db.Text)
    contributions = db.relationship('Contribution', backref='editathon', lazy=True)

class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.String(255), primary_key=True)  # Using Wikimedia username
    registration_date = db.Column(db.Date)
    contributions = db.relationship('Contribution', backref='user', lazy=True)

class Contribution(db.Model):
    __tablename__ = 'contributions'
    contribution_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), db.ForeignKey('users.user_id'), nullable=False)
    editathon_id = db.Column(db.Integer, db.ForeignKey('editathons.editathon_id'), nullable=False)
    project = db.Column(db.String(50), nullable=False)
    article_title = db.Column(db.String(255), nullable=False)
    submission_timestamp = db.Column(db.TIMESTAMP, server_default=func.now())
    acceptance_status = db.Column(db.Boolean, default=False)

# --- API Endpoints ---

@app.route('/')
def list_campaigns():
    campaigns = Campaign.query.all()
    return render_template('index.html', campaigns=campaigns)

@app.route('/campaign/<campaign_name>&<int:year>')
def campaign_overview(campaign_name, year):
    campaign = Campaign.query.filter_by(name=campaign_name, year=year).first_or_404()
    editathons = campaign.editathons
    project_stats = get_campaign_project_stats(campaign.campaign_id)
    user_stats = get_campaign_user_stats(campaign.campaign_id)
    return render_template('campaign_overview.html', campaign=campaign, editathons=editathons, project_stats=project_stats, user_stats=user_stats)

@app.route('/campaign/<campaign_name>&<int:year>/<sitename>')
def editathon_overview(campaign_name, year, sitename):
    campaign = Campaign.query.filter_by(name=campaign_name, year=year).first_or_404()
    editathon = Editathon.query.filter_by(campaign_id=campaign.campaign_id, sitename=sitename).first_or_404()
    project_stats = get_editathon_project_stats(editathon.editathon_id)
    user_stats = get_editathon_user_stats(editathon.editathon_id)
    return render_template('editathon_overview.html', campaign=campaign, editathon=editathon, project_stats=project_stats, user_stats=user_stats)

# --- API Endpoints for Data (for frontend to fetch) ---

@app.route('/api/campaigns')
def api_list_campaigns():
    campaigns = Campaign.query.all()
    campaign_list = [{'id': c.campaign_id, 'name': c.name, 'year': c.year} for c in campaigns]
    return jsonify(campaigns=campaign_list)

@app.route('/api/campaigns/<int:campaign_id>')
def api_campaign_details(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    editathons = [{'id': e.editathon_id, 'sitename': e.sitename} for e in campaign.editathons]
    project_stats = get_campaign_project_stats(campaign_id)
    user_stats = get_campaign_user_stats(campaign_id)
    return jsonify(campaign={'id': campaign.campaign_id, 'name': campaign.name, 'year': campaign.year, 'description': campaign.description, 'editathons': editathons, 'project_stats': project_stats, 'user_stats': user_stats})

@app.route('/api/campaigns/<int:campaign_id>/editathons')
def api_campaign_editathons(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    editathons = [{'id': e.editathon_id, 'sitename': e.sitename} for e in campaign.editathons]
    return jsonify(editathons=editathons)

@app.route('/api/campaigns/<int:campaign_id>/<sitename>')
def api_editathon_details(campaign_id, sitename):
    editathon = Editathon.query.filter_by(campaign_id=campaign_id, sitename=sitename).first_or_404()
    project_stats = get_editathon_project_stats(editathon.editathon_id)
    user_stats = get_editathon_user_stats(editathon.editathon_id)
    return jsonify(editathon={'id': editathon.editathon_id, 'sitename': editathon.sitename, 'project_stats': project_stats, 'user_stats': user_stats})

# --- Data Aggregation Functions ---

def get_campaign_project_stats(campaign_id):
    results = db.session.query(
        Contribution.project,
        func.count(distinct(Contribution.user_id)),
        func.count(Contribution.article_title),
        func.sum(case([(Contribution.acceptance_status == True, 1)], else_=0))
    ).join(Editathon).filter(Editathon.campaign_id == campaign_id).group_by(Contribution.project).all()
    return [{'project': res[0], 'users': res[1], 'articles': res[2], 'accepted_articles': res[3]} for res in results]

def get_campaign_user_stats(campaign_id):
    results = db.session.query(
        User.user_id,
        func.count(Contribution.article_title),
        func.sum(case([(Contribution.acceptance_status == True, 1)], else_=0)),
        func.group_concat(distinct(Contribution.project))
    ).join(Contribution).join(Editathon).filter(Editathon.campaign_id == campaign_id).group_by(User.user_id).all()
    return [{'user': res[0], 'articles': res[1], 'accepted_articles': res[2], 'projects': res[3].split(',')} for res in results]

def get_editathon_project_stats(editathon_id):
    results = db.session.query(
        Contribution.project,
        func.count(distinct(Contribution.user_id)),
        func.count(Contribution.article_title),
        func.sum(case([(Contribution.acceptance_status == True, 1)], else_=0))
    ).filter(Contribution.editathon_id == editathon_id).group_by(Contribution.project).all()
    return [{'project': res[0], 'users': res[1], 'articles': res[2], 'accepted_articles': res[3]} for res in results]

def get_editathon_user_stats(editathon_id):
    results = db.session.query(
        User.user_id,
        func.count(Contribution.article_title),
        func.sum(case([(Contribution.acceptance_status == True, 1)], else_=0)),
        func.group_concat(distinct(Contribution.project))
    ).join(Contribution).filter(Contribution.editathon_id == editathon_id).group_by(User.user_id).all()
    return [{'user': res[0], 'articles': res[1], 'accepted_articles': res[2], 'projects': res[3].split(',')} for res in results]

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
    app.run(debug=True) # Disable debug mode in production on Toolforge

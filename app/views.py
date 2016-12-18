import os
import json

from facebook import get_user_from_cookie, GraphAPI
from flask import g, render_template, redirect, request, Response, session, url_for

from app import app, db
from models import User
from feed_maker import get_user_feed, get_user_links

# Facebook app details
FB_APP_ID = app.config['FB_APP_ID']
FB_APP_NAME = app.config['FB_APP_NAME']
FB_APP_SECRET = app.config['FB_APP_SECRET']
# Cache lifespans
CACHE_LIFE_LINKS = app.config['CACHE_LIFE_LINKS']
CACHE_LIFE_RSS = app.config['CACHE_LIFE_RSS']

# LKG directory
LKG_DIR = os.path.join(app.config['BASE_DIRECTORY'], '_lkg')

# Get an access token from the database
def get_access_token(user_id):
    """ Attempts to load an access token from a user id """
    user = User.query.filter(User.id == user_id).first()
    if user and user.access_token:
        return user.access_token
    else:
        return False

# LKG is "last known good" which handles cases where cache and access token have expired 
def set_lkg(user_id, data, prefix='links-'):
    """ Puts a last known good value """
    if not os.path.exists(LKG_DIR):
        os.makedirs(LKG_DIR)
    with open(os.path.join(LKG_DIR, prefix+user_id), "w") as f:
        f.write(data)

def get_lkg(user_id, prefix='links-'):
    """ Gets a last known good value """
    f_loc = os.path.join(LKG_DIR, prefix+user_id) 
    if not os.path.exists(f_loc):
        return False
    else:
        with open(f_loc, "r") as f:
            return f.read()


# RSS Feed
@app.route('/fb/<user_id>.rss', methods=['GET'])
@app.cache.cached(timeout=CACHE_LIFE_RSS)
def rss_feed(user_id):
    """ An RSS feed """
    access_token = get_access_token(user_id)
    try:
        graph = GraphAPI(access_token)
        rss = get_user_feed(graph, user_id).rss_str()
        set_lkg(user_id, rss, prefix='rss-')
        return Response(rss, mimetype='text/xml')
    except:
        try:
            return Response(get_lkg(user_id, prefix='rss-'), mimetype='text/xml')
        except:
            pass
    # Otherwise, a user is not logged in.
    return render_template('login.html', app_id=FB_APP_ID, name=FB_APP_NAME)


# Links list
@app.route('/fb/<user_id>', methods=['GET'])
@app.cache.cached(timeout=CACHE_LIFE_LINKS)
def links_list(user_id):
    """ An alphabetical list of websites """
    access_token = get_access_token(user_id)
    try:
        graph = GraphAPI(access_token)
        links = get_user_links(graph, user_id, num_pages=5)
        set_lkg(user_id, json.dumps(links), prefix='links-')
        return render_template('list.html', links=links, app_id=FB_APP_ID, name=FB_APP_NAME)
    except:
        try:
            return render_template('list.html', links=json.loads(get_lkg(user_id, prefix='links-')), app_id=FB_APP_ID, name=FB_APP_NAME)
        except:
            pass
    # Otherwise, a user is not logged in.
    return render_template('login.html', app_id=FB_APP_ID, name=FB_APP_NAME)


@app.route('/privacy-policy.html')
def privacy():
    return render_template('privacy.html')

#
# Boilerplate FB App stuff
#
@app.route('/')
def index():
    # If a user was set in the get_current_user function before the request,
    # the user is logged in.
    if g.user:
        return render_template('index.html', 
            app_id=FB_APP_ID,
            app_name=FB_APP_NAME, 
            user=g.user)
    # Otherwise, a user is not logged in.
    return render_template('login.html', app_id=FB_APP_ID, name=FB_APP_NAME)


@app.route('/logout')
def logout():
    """Log out the user from the application.

    Log out the user from the application by removing them from the
    session.  Note: this does not log the user out of Facebook - this is done
    by the JavaScript SDK.
    """
    session.pop('user', None)
    return redirect(url_for('index'))


@app.before_request
def get_current_user():
    """Set g.user to the currently logged in user.

    Called before each request, get_current_user sets the global g.user
    variable to the currently logged in user.  A currently logged in user is
    determined by seeing if it exists in Flask's session dictionary.

    If it is the first time the user is logging into this application it will
    create the user and insert it into the database.  If the user is not logged
    in, None will be set to g.user.
    """

    # Set the user in the session dictionary as a global g.user and bail out
    # of this function early.
    if session.get('user'):
        g.user = session.get('user')
        return

    # Attempt to get the short term access token for the current user.
    result = get_user_from_cookie(cookies=request.cookies, app_id=FB_APP_ID,
                                  app_secret=FB_APP_SECRET)

    # If there is no result, we assume the user is not logged in.
    if result:
        # Check to see if this user is already in our database.
        user = User.query.filter(User.id == result['uid']).first()

        if not user:
            # Not an existing user so get info
            graph = GraphAPI(result['access_token'])
            extended_token = graph.extend_access_token(app_id=FB_APP_ID, app_secret=FB_APP_SECRET)
            access_token = extended_token['access_token'] if extended_token else result['access_token']

            profile = graph.get_object('me')
            if 'link' not in profile:
                profile['link'] = ""

            # Create the user and insert it into the database
            user = User(id=str(profile['id']), name=profile['name'],
                        profile_url=profile['link'],
                        access_token=access_token)
            db.session.add(user)
        elif user.access_token != result['access_token']:
            # If an existing user, update the access token
            user.access_token = result['access_token']

        # Add the user to the current session
        session['user'] = dict(name=user.name, profile_url=user.profile_url,
                               id=user.id, access_token=user.access_token)

    # Commit changes to the database and set the user as a global g.user
    db.session.commit()
    g.user = session.get('user', None)

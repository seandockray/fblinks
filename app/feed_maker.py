#!venv/bin/python
# -*- coding: utf-8 -*-

"""
Builds feeds
"""
from dateutil.parser import parse
from urlparse import urlparse
import facebook
import requests
from feedgen.feed import FeedGenerator
from tld import get_tld
from tld.utils import update_tld_names

update_tld_names()

def pp(post):
    """ Here you might want to do something with each post. E.g. grab the
    post's message (post['message']) or the post's picture (post['picture']).
    In this implementation we just print the post's created time.
    """
    from pprint import pprint
    pprint(post)


def add_to_feed(post, feed_entry, id="feed_id"):
    """ Add the post to a feed """
    c_time = parse(post['created_time'])
    u_time = parse(post['updated_time'])
    feed_entry.id('http://links.metadada.xyz/fb/%s/%s' % (id,post['id']))
    feed_entry.pubdate(pubDate=c_time)
    feed_entry.updated(updated=u_time)
    title = post['name'] if 'name' in post else 'Untitled'
    feed_entry.link(link={'href':post['link'], 'title': title})
    feed_entry.title(title=title)
    summary = ''
    if 'picture' in post and post['picture'] is not None:
        summary = '<img src="%s"><br/>%s' % (post['picture'], summary)
    if 'description' in post:
        summary = '%s<p>"%s"</p>' % (summary, post['description'])
    if 'message' in post:
        summary = '%s<p>%s</p>' % (summary, post['message'])
    if summary:
        feed_entry.summary(summary=summary)

def construct_feed(links, id=''):
    """ Constructs a feed from a list of links """
    fg = FeedGenerator()
    fg.id('http://links.metadada.xyz/fb/'+id)
    fg.title('links')
    fg.subtitle('links from your friends without the ads, memoir, or auto-playing videos')
    fg.link( href='http://links.metadada.xyz/', rel='self' )
    for l in links:
        add_to_feed(l, fg.add_entry(), id=id)
    return fg

def get_links_for_user(graph, user_id, num_pages=1):
    """ Gets a list of links posts for a user """
    profile = graph.get_object(user_id)
    links = []
    args = {'fields' : 'link,name,created_time,updated_time,message,picture,description', }
    posts = graph.get_connections(user_id, 'posts', **args)
    if 'data' in posts and posts['data']:
        curr_page = 0
        while curr_page<num_pages:
            try:
                #[pp(post) for post in posts['data']]
                links.extend([post for post in posts['data'] if 'link' in post])
                posts = requests.get(posts['paging']['next']).json()
                curr_page += 1
            except KeyError:
                break
    return links

def get_friends_for_user(graph, user_id):
    """ Gets a list of friends (who have installed the app) """
    friends = graph.get_object("%s/friends" % user_id)
    user_ids = []
    if 'data' in friends and friends['data']:
        user_ids = [f['id'] for f in friends['data']]
    return user_ids

def get_user_feed(graph, user_id):
    """ For a user id, get an RSS feed """
    friends = get_friends_for_user(graph, user_id)
    links = get_links_for_user(graph, user_id)
    for f_id in friends:
        links.extend(get_links_for_user(graph, f_id))
    return construct_feed(links, id=user_id)


def get_user_links(graph, user_id, num_pages=1, filter_num=0):
    """ For a user id, get an RSS feed """
    friends = get_friends_for_user(graph, user_id)
    links = get_links_for_user(graph, user_id, num_pages=num_pages)
    for f_id in friends:
        links.extend(get_links_for_user(graph, f_id))
    base_links = {}
    for link in links:
        try:
            res = get_tld(link['link'], as_object=True)
            tld = "%s.%s" % (res.subdomain, res.tld) if res.subdomain not in ['www',''] else res.tld
        except:
            tld = link['link']
        # special case handling
        if tld in ['t.co','facebook.com']:
            continue
        if tld in ['twitter.com','github.com']:
            after = link['link'].split(tld)[1].split('/')[1]
            if after:
                tld = tld + "/" + after
        if tld not in base_links:
            base_links[tld] = 0
        base_links[tld] += 1
    filtered = {k:v for k,v in base_links.iteritems() if v>filter_num}
    return filtered

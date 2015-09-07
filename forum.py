#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import torndb
from tornado.options import define,options
import bcrypt
import concurrent.futures
from tornado import gen
import tornado.escape
#import markdown
import json
import tornado.gen
import tornado.httpclient
import urllib

define("port",default=8003,help='run on the given port',type=int)
define('mysql_host',default='127.0.0.1:3306',help='db host')
define('mysql_database',default='blog2',help='db name')
define('mysql_user',default='root',help='db user')
define('mysql_password',default='1',help='db password')
executor = concurrent.futures.ThreadPoolExecutor(2)

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates")
STATIC_PATH = os.path.join(os.path.dirname(__file__), "static")

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/login',LoginHandler),
            (r'/',HomeHandler),
            (r'/logout',LogoutHandler),
            (r'/register',RegisterHandler),
            (r'/post',PostHandler),
            (r'/(\d+)',ArticleHandler),
	        (r'/rss',V2exHandler),
            (r'/test',AjaxHandler),
            (r'/ajax',ForHandler),
            (r'/feedly',FeedlyHandler),
            (r'/upload',UploadHandler),
            (r'/day',DailyHandler),
        ]
        settings = dict(
            template_path = TEMPLATE_PATH,
            static_path = STATIC_PATH,
            debug = True,
            cookie_secret = 'bZJc2sWbQLKos6GkHn/VB9oXwQt8S0R0kRvJ5/xJ89E=',
            login_url = '/login',
            ui_modules = {'Hello':HelloModule,'Reply':ReplyModule},
        )
        tornado.web.Application.__init__(self,handlers,**settings)
        self.db = torndb.Connection(
            host = options.mysql_host,
            database = options.mysql_database,
            user = options.mysql_user,
            password = options.mysql_password,
        )

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie('username')


class LoginHandler(BaseHandler):
    def get(self):
        self.render('login.html',error=None)
    @gen.coroutine
    def post(self):
        name = self.get_argument('username')
        password = self.get_argument('password')
        check_result = self.check(name,password)
        if isinstance(check_result,dict):
            hashed_password = yield executor.submit(
            bcrypt.hashpw, tornado.escape.utf8(password),
            tornado.escape.utf8(check_result['password']))

            if hashed_password == check_result['password']:

                self.set_secure_cookie('username',name)
                self.redirect('/')
            else:
                self.render('login.html',error='密码错误')
        elif check_result == 3:
            self.render('login.html',error='用户名不存在')
        else:
            self.render('login.html',error='请输入完整')


    def check(self,name,password):
        db = self.application.db
        all = db.query('select * from users')
        if name and password:
            if name in [i['username'] for i in all ]:
                sql = 'select * from users where username="%s"' %name
                db_name = db.get(sql)
                return db_name
            else: return 3
        else: return 4


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie('username')
        self.redirect(self.get_argument('next','/'))


class RegisterHandler(BaseHandler):
    def get(self):
        self.render('register.html',error=None)
    @gen.coroutine
    def post(self):
        username = self.get_argument('username')
        password = self.get_argument('password')
        email = self.get_argument('email')
        db = self.application.db
        check_register_result = self.check_register(username,password,email)
        if check_register_result == 1:
            hashed_password = yield executor.submit(
                 bcrypt.hashpw,tornado.escape.utf8(password),bcrypt.gensalt()
             )
            db.insert("insert into users (username,password,email) values (%s,%s,%s)",username,hashed_password,email)
            self.set_secure_cookie('username',username)
            self.redirect('/')
        elif check_register_result == 2:
            self.render('register.html',error='该邮箱注册过')
        elif check_register_result == 3:
            self.render('register.html',error='用户名已被注册')
        else:
            self.render('register.html',error='请输入完整')
    def check_register(self,username,password,email):
        db = self.application.db
        all = db.query('select * from users')

        if username and password and email:
            if username not in [i['username'] for i in all ]: #用户名在数据库里没有
                if email not in [i['email'] for i in all ]: return 1 #都没有
                else: return 2 #邮箱存在，用户名不存在
            else: return 3 #用户名在数据库里有，已存在
        else:
            return 4


class HomeHandler(BaseHandler):
    def get(self):
        all = self.application.db.query('select * from article order by posttime desc')
        if not all:
            self.redirect('/post')
            return
        self.render('home.html',all=all)

class PostHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render('post.html')

    @tornado.web.authenticated
    def post(self):
        title = self.get_argument('title')
        content = self.get_argument('content')
        author = self.current_user
        self.application.db.insert('insert into article (title,content,author) values (%s,%s,%s)',title,content,author)
        self.redirect('/')


class ArticleHandler(BaseHandler):
    def get(self,id):
        one = self.application.db.get("select * from article where id = %s",id)
        if not one: raise tornado.web.HTTPError(404)
        comments = self.application.db.query('select * from comment where id = %s order by reply_time desc',id)
	mistake = None
        self.render('page.html',one = one,comments=comments,mistake = mistake)
        #return id

    def post(self,id):
        comment = self.get_argument('comment')
        reply_user = self.current_user
        if (not comment):
            one = self.application.db.get('select * from article where id =%s',id)
            comments = self.application.db.query('select * from comment where id = %s order by reply_time desc',id)
            self.render('page.html',one = one,comments = comments ,mistake = u'回复内容不能为空')
        # reply_user = self.current_user
        # sql = 'insert into comment (id,reply_user,comment) values(%s,%s,%s)' %(id,reply_user,comment)
        else :
            self.application.db.insert('insert into comment (id,reply_user,comment) values(%s,%s,%s)',id,reply_user,comment)
            self.redirect('/%s'%id)

class HelloModule(tornado.web.UIModule):
    def render(self,i):
        return self.render_string('modules/item.html',i=i)

class ReplyModule(tornado.web.UIModule):
    def render(self,i):
        return self.render_string('modules/reply-item.html',i=i)

class V2exHandler(BaseHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        client = tornado.httpclient.AsyncHTTPClient()
        response = yield client.fetch('https://www.v2ex.com/api/topics/hot.json')
        if response.code == 200:
            items = json.loads(response.body.decode('utf-8'))
            title = u'V2EX'
            description = u'V2EX 是创意工作者们的社区。这里目前汇聚了超过 110,000 名主要来自互联网行业、游戏行业和媒体行业的创意工作者。V2EX 希望能够成为创意工作者们的生活和事业的一部分。'
            #pubdate = items[0]['created']
            #link = 'http://daily.zhihu.com/'
            self.set_header("Content-Type", "application/rss+xml; charset=UTF-8")
            self.render("rss.xml", title=title, description=description, items=items)
        else:
            raise tornado.web.HTTPError(response.code)

class ForHandler(BaseHandler):
    def get(self):
        self.render('ajax.html')

class AjaxHandler(BaseHandler):
    def post(self):
        self.write(self.get_argument('message'))

class FeedlyHandler(BaseHandler):
    def get(self):
        self.render('feedly.html',b=None,error=None)

    @tornado.gen.coroutine
    def post(self):
        site = self.get_argument('site')
        if site:
            quote_site = urllib.quote_plus(site)
            long_url = 'https://feedly.com//v3/search/auto-complete?cv=28.0.982&ck=1437809329022&locale=en-US&query=' + quote_site + '&sites=6&topics=0&libraries=0'
            client = tornado.httpclient.AsyncHTTPClient()
            response = yield client.fetch(long_url)
            content = response.body.decode('utf-8')
            items =  json.loads(content)
            a = items.get('sites')
            b = {}
            for i in a:
                rss_url = i.get('feedId').split('feed/',1)[-1]
                subscribers = i.get('subscribers')
                b[rss_url] = subscribers if subscribers else 0
            self.render('feedly.html',b=b,error=None)
        else:
            self.render('feedly.html',b=None,error='Nooooooooooo!')

class UploadHandler(BaseHandler):
    def get(self):
        self.render('upload_file.html')

    def post(self):
        if self.request.files:
            myfile = self.request.files['myfile'][0]
            print myfile
            filename = myfile['filename']
            path = '/home/mako/0619/'+filename
            print path
            fin = open(path,'w')
            print 'success'
            fin.write(myfile['body'])
            fin.close()

class DailyHandler(BaseHandler):
    def get(self):
        sql_day_all = "select * from helishi"
        count = len(self.application.db.query(sql_day_all))
        offset = int(self.get_argument('offset',0))
        #limit = self.get_argument('limit',15)
        sql_day = "select * from helishi limit %d,15" % offset

        if offset == 0:
            if count > 15:
                before = None
                after = 15
            else:
                before =None
                after = None
        else:
            if (count - 15) / 15.0 > 1:
                before = offset - 15
                after = offset + 15
            if 0 < (count - 15) / 15.0 < 1:
                before = offset - 15
                after = None

        news_list = self.application.db.query(sql_day)
        self.render('day.html',news_list=news_list,after=after,before=before)

if __name__ == "__main__":
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

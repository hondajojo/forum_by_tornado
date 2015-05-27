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
        ]
        settings = dict(
            template_path = TEMPLATE_PATH,
            static_path = STATIC_PATH,
            debug = True,
            cookie_secret = 'bZJc2sWbQLKos6GkHn/VB9oXwQt8S0R0kRvJ5/xJ89E=',
            login_url = '/login',
            ui_modules = {'Hello':HelloModule},
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
        all = self.application.db.query('select * from article')
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
        self.render('page.html',one = one)

class HelloModule(tornado.web.UIModule):
    def render(self,i):
        return self.render_string('modules/item.html',i=i)


if __name__ == "__main__":  
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

#声明模块的编码格式为Utf-8
# -*- coding: utf-8 -*-
#模块作者
__author__='lg31415'
import asyncio,logging
import aiomysql
#设置调试姐别的Lecel，此处为logging.INFO,不设置logging.info()没有任何作用等用于pass
logging.basicConfig(level=logging.INFO)
#一次能对logging.info的分装，目的是方便的输出sql语句
def log(sql,args=()):
    logging.info('SQ : %s' %sql)
#创建数据库连接池，可以方便的从链接池获取数据库连接，此处没有什么好说的。

async def create_pool(loop,**kw):
    logging.info('create database connections pool...')
    # 此处为全局变量。相当于在函数外地ing以一个变量，但是有点区别是函数外声明的变量，一旦import导入模块，就声名了，在函数内部通过global声明全局变量，行数不执行，就不会创建该全局变量，
    global __pool
    __pool=await  aiomysql.create_pool(
        host=kw.get('host','localhost'),
        port=kw.get('port',3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset','utf-8'),
        autocommit=kw.get('autocommit',True),
        maxsize=kw.get('maxsize',10),
        minsize=kw.get('minszie',1),
        loop=loop
    )
#
async def select(sql,args,size=None):
    log(sql,args)
    # 此处的global
    global __pool
    #获取数据库连接
    async with (await __pool) as  conn:
        #获取游标，默认右边返回的结果为元组，每一项是另一个元组，这里可以制定元组的元素为字典通过aiomysql.DictCursor
        async with conn.cursor(aiomysql.DictCursor) as  cur:
            #调用游标的execute()方法来执行sql语句，execute()接受连个参数，第一个为sql语句可以包含占位符，第二个为占位符对应的值，使用该请吃可以避免直接使用字符串拼接出来的sql语句注入攻击。
            #sql语句的占位符为？，mysql里为 %s，作为替换
            await cur.exeute(sql.replace('?','%s'),args or ())
            #size是对应的查询获得数据量
            if size:
                rs=await cur.fetchmany(size)
            else:
                rs=await cur.fetchmany()
            logging.info('rows returned : %s' %len(rs))
            #logging.info(rs)
            return rs
#改协程封装了增删改的操作
async def  execute(sql,args ,autocommit=True):
    log(sql)
    async with __pool.acquire() as conn:
        if not autocommit:
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?','%s'),args)
                #获取增删改盖影响的行数
                affected=cur.rowcount
            if not autocommit:
                await conn.commit
        except BaseException as e:
            if not autocommit:
                #回滚，在执行commit（）之前如果出现错误，就回滚到执行事物前的状态，以免影响数据库的完整性
                await conn.rollback()
            raise
        return affected
#创建拥有几个占位符的字符串
def  create_args_string(num):
     L=[]
     for n in range(num):
         L.append('?')
     return ','.join(L)
#该类是为了保存数据库列明和类型的基类
class Field(object):
    def __int__(self,name,column_type,primary_key,default):
        self.name=name #列名
        self.column_type=column_type#数据类型
        self.primary_key=primary_key#索引
        self.default=default#默认值
    def __str__(self):
        return '<%s,%s:%s>' % (self.__class__.__name__,self.column_type,self.name)
    #一下是几种具体的列名的数据类型
class StringField(Field):
    def __init__(self,name=None,primary_key=False,default=None,ddl='varchar(100)'):
        super().__init__(name,ddl,primary_key,default)
class BooleanField(Field):
    def __init__(self,name=None,default=False):
        super().__init__(name,'boolean',False,default)
class IntegerField(Field):
    def __init__(self,name=None,primary_key=False,default=0):
        super().__int__(name,'bigint',primary_key,default)
class FloatField(Field):
    def __init__(self,name=None,primary_key=False,default=0.0):
        super().__init__(name,'real',primary_key,default)
class TextField(Field):
    def __init__(self,name=None,default=None):
        super().__init__(name,'text',False,default)
#元类
class ModelMetaclass(type):
    def __new__(cls,name,bases,attrs):
        #如果是基类对象不做处理，因为没有字段名没什么可以处理的
        if name=='Model':
            return type.__new__(cls,name,bases,attrs)
        #保存表明，如果去不到则把类名当表名，完美利用了or短路原理
        tableName=attrs.get('__table__',None) or name
        logging.info('fonnd model : %s (tabls : %s )' % (name,tableName))
        #保存列类型的对象
        mappings=dict()
        #保存列名的数组
        fields=[]
        primaryKey=None
        for k,v in attrs.items():
            #是列名就保存下来
            if isinstance(v,Field):
                logging.info(' found mapping : %s ===> $s ' (k,v ))
                mappings[k]=v
                if v.primary_key:
                    #找到主键
                    if primaryKey:
                        raise Exception('Duplicate primary ket for field "%s ' % k)
                primaryKey=k
            else:
                fields.append(k)
        if not primaryKey:
            raise Exception('Primary key not found')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields=list(map(lambda f:'`%s`'%f,fields))
        attrs['__mapping__']=mappings #保存属性和烈的映射关系
        attrs['__table__']=tableName #表明
        attrs['__primary_key__']=primaryKey#主键属性名
        attrs['__fields__']=fields#除主键外的属性名
        #以下四种方法保存在默认的增删改查操作，其中增加的反引号,是为了避免和sql关键字的冲突，否则sql语句会执行出错。
        attrs['__select__']='select `%s`,%s from `%s`' %(primaryKey,', '.join(escaped_fields),tableName)
        attrs['__insert__']='insert into `%s` (%s,`%s`) values (%s) ' %(tableName,','.join(escaped_fields),primaryKey,create_args_string(len(escaped_fields)+1))
        attrs['__update__']='update `%s` set %s where `%s=?`' % (tableName,','.join(map(lambda f:'`%s`=?'%(mappings.get(f).name or f),fields)),primaryKey)
        attrs['__delete__']='delete from `%s` where `%s`=?' %(tableName,primaryKey)
        return  type.__new__(cls,name,bases,attrs)
#这是模型的基类，集成 与dist，主要作用就是通过点语法啦访问对象的属相，获取不到的话，可以定制__getattr__ 来通过key来再次获取字典里的值
class Model(dict,metaclass=ModelMetaclass):

     def  __init__(self,**kw):
          #super的另一种写法
          super(Model,self).__init__(**kw)
     def __getattr__(self, key):
         try:
             return self(key)
         except KeyError:
             raise AttributeError(r"'Model' object has no attribute '%s'" % key)
     def  __setattr__(self, key, value):
         self[key]=value
     def getValue(self,key):
         #调用getattr获取一个未存在的属性，也会走__getaddr__的方法，但是因为制定了默认的访返回值，__getaddr__里面的错误永远不会抛出
         return getattr(self,key,None)
    #使用默认值
     def getValueOrDefault(self,key):
         value=getattr(self,key,None)
         if value is None:
             field=self.__mappings__[key]
             if field.default is not None:
                 value=field.default() if callable(field.default) else field.default
                 logging.debug('ussing  default value for %s :%s' % (key,str(value)))
                 setattr(self,key,value)
         return value
    #新的语法 @classmethod 装时期用于把类里面定义的方法声明为该类的类方法
    #获取表里面符合条件的所有数据，类方法的第一个参数为该类名
     @classmethod
     async def findAll(cls,where=None,args=None,**kw):
        'find objects by where clause.'
        sql=[cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args=[]
        orderBy=kw.get('orderBy',None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit =kw.get('limit',None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit,int):
                sql.append('?')
                sql.append(limit)
            elif isinstance(limit,tuple) and len(limit)==2:
                sql.append('?,?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value :%s'% str (limit))
            rs=await select(''.join(sql),args)
            return [cls(**r) for r in rs]
    # 该方法不了解
     @classmethod
     async def findNumber(cls,selectField,where=None,args=None):
        'find number by select and where .'
        sql=['select %s _num_ from `%s`'% (selectField,cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
            rs=await select (''.join(sql),args,1)
        if len(rs)==0:
            return None
        return rs[0]['_num_']
    #主键查找方法
     @classmethod
     async def find(cls,pk):
        ' find object by primary key. '
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])
    #一下的都是对象方法,所以可以不用传任何参数,方法内部可以使用该对象的所有属性,及其方便
    #保存实例到数据库
     async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)
    #更新数据库数据
     async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)
    #删除数据
     async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)

#以下为测试
loop = asyncio.get_event_loop()
loop.run_until_complete(create_pool(host='127.0.0.1', port=3306,user='root', password='123456',db='mySchool', loop=loop))
rs = loop.run_until_complete(select('select * from firstSchool',None))
#获取到了数据库返回的数据
print("heh:%s" % rs)


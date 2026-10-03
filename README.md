# CNC机加工厂生产管理系统

在原有进销存、基础资料和工作流上，增加小规模机加车间的生产管理：设备、刀具、夹具、工艺、工单、工序报工、质检、物料批次、数控程序、图纸和外协。这些对象都有二维码。手机打开 `/m/` 后可以扫码开工、报工、质检、发料，并查看在制、交期、设备、质量、员工产量、外协和刀具寿命报表。

管理后台仍是 `/admin/`。入口页同时提供车间手机端和后台。

# Django-ERP
Django-ERP是一款基于Django开发的ERP管理软件，包含常用的销售管理、采购管理、库存管理、组织管理等，支持按项目归集费用，支持工作流审批，支持采购单、报价单的批量导入。

Forked from <a href="https://github.com/zhuinfo/Django-ERP">zhuinfo Django-ERP</a> 感谢他的付出, 和其他网友的辛勤付出。

# 安装指南

解释器和依赖都放在项目目录里，不写入系统环境变量。

- Python 3.14.8：`.python\python.exe`
- 虚拟环境：`.venv`（由上面的解释器创建）
- Django 6.1.1 及其他依赖见 `requirements.txt`
- MySQL 8.4.11：`.mysql\mysql-8.4.11-winx64`，端口 `3307`，只监听本机。系统里原来的 MySQL 5.7 没有改动。

安装或更新依赖：

```
.python\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动数据库和网站（使用项目自带的 Python 和 MySQL）：

```
.\start.bat
```

打开 http://127.0.0.1:8000 ，后台是 /admin/ ，手机是 /m/ 。登录账号 admin，密码 admin。

## 数据库配置

数据库配置项在mis/settings.py文件中
在88-96行为Mysql数据库配置

```
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',#MYSQL类型数据库，Python会依赖MySQL的驱动器
        'HOST': 'localhost',#数据库主机地址
        'NAME': 'mis',#数据库名称
        'USER': 'root',#数据库用户名（建议不要加入root敢死队）
        'PASSWORD': 'root',#数据库密码
    }
}
```


## 克隆代码
> git clone https://github.com/bg4hkq/Django-ERP.git

## 创建数据库
 create database  `mis`   DEFAULT CHARACTER SET  utf8mb4;
## 导入数据库

> mysql -uroot -proot mis < Install/mis.sql

## 运行测试服务器
> .\start.bat

## 修改管理员账户密码
```
C:\Django-ERP>python manage.py changepassword admin

You have 3 unapplied migration(s). Your project may not work properly until you apply the migrations for app(s): admin, auth.
Run 'python manage.py migrate' to apply them.
Changing password for user 'admin'
Password:
Password (again):
Password changed successfully for user 'admin'

C:\Django-ERP>
```

# 排错

## MYSQL驱动错误
```
django.core.exceptions.ImproperlyConfigured: Error loading MySQLdb module: No module named MySQLdb
```

出现No module named MySQLdb是django找不到MySQL驱动导致的问题，所以需要先安装一个数据库驱动。


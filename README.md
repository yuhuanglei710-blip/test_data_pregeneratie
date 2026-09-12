# test_data_pregeneratie
预生成各类测试数据，后端接口+数据库修改+后台接口集成，实现复杂功能，为功能测试赋能
## 目录结构
- tools:
    工具类如时间戳等存放目录
- api
    前后端API等存放目录
- base
    user、枚举等基类存放目录
- test
    测试用例存放目录
- main.py
    入口函数
- cache
    缓存目录，用于存储token等临时数据
- README.md
    食用说明
- requirements.txt
    项目依赖文件
    项目依赖：
- .env
    环境变量文件配置
## 使用方法
1.下载安装python环境
```
pip install -r requirements.txt
```


2.创建填写.env文件，并配置环境变量

3.运行main.py
```
python main.py
```

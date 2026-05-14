"""Market Data Package - 独立启动入口

启动方式:
    python app.py

访问地址:
    http://127.0.0.1:5000/
"""

import logging
import os
import sys

# 确保项目根目录（markets 的父目录）在 Python 路径中
# 这样 import markets.xxx 才能正确解析
PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class F(logging.Formatter):
    C={10:'\033[36m',20:'\033[37m',30:'\033[33m',40:'\033[31m',50:'\033[31;1m'}
    def format(self,r):return f"{self.C.get(r.levelno,'')}{super().format(r)}\033[0m"

h=logging.StreamHandler()
h.setFormatter(F('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().handlers=[h]
logging.getLogger().setLevel(logging.INFO)

from app.api_service import DataQualityAPIService

# 创建服务实例（无需 quality_monitor）
api_service = DataQualityAPIService()
app = api_service.app

if __name__ == '__main__':
    print("=" * 50)
    print("Market Data Package 已启动")
    print("访问地址: http://127.0.0.1:8001/")
    print("数据浏览器: http://127.0.0.1:8001/explorer")
    print("=" * 50)
    app.run(host='127.0.0.1', port=8001, debug=True)

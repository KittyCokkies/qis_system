# =============================================================================
# QIS System - Airflow Docker Image
# Python 3.12 + Airflow 2.8
# =============================================================================

FROM apache/airflow:2.8.3-python3.12

USER root

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
RUN mkdir -p /opt/qis_system && chown -R airflow:airflow /opt/qis_system

USER airflow

# 安装项目依赖（分步以利用Docker缓存）
COPY --chown=airflow:root requirements.txt /tmp/requirements.txt

# 先安装Airflow稳定版本的核心依赖
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 安装项目依赖（排除可能与Airflow冲突的包）
RUN grep -v '^WindPy' /tmp/requirements.txt | \
    grep -v '^riskfolio' | \
    xargs -I {} pip install --no-cache-dir {} || true

# 安装数据库驱动
RUN pip install --no-cache-dir \
    pymysql>=1.1.0 \
    psycopg2-binary>=2.9.0

# 验证安装
RUN python -c "import sqlalchemy; print(f'SQLAlchemy: {sqlalchemy.__version__}')" && \
    python -c "import pandas; print(f'Pandas: {pandas.__version__}')" && \
    python -c "import airflow; print(f'Airflow: {airflow.__version__}')"

# 设置环境变量
ENV PYTHONPATH=/opt/airflow:/opt/qis_system
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/airflow

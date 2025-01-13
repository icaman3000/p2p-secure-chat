import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.utils.database import Base

TEST_DB = 'test.db'

@pytest.fixture(scope="session")
def test_engine():
    """创建测试数据库引擎"""
    # 如果测试数据库已存在，删除它
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    # 创建测试数据库引擎
    engine = create_engine(f'sqlite:///{TEST_DB}')
    
    # 创建所有表
    Base.metadata.create_all(engine)
    
    yield engine
    
    # 测试结束后清理
    Base.metadata.drop_all(engine)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@pytest.fixture(scope="function")
def test_session(test_engine):
    """创建测试会话"""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    yield session
    
    # 清理会话
    session.close()
    
    # 清理表数据
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit() 
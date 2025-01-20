from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox
)
from PyQt6.QtCore import pyqtSignal
from src.utils.database import register_user, verify_user, init_database
from sqlalchemy.orm import Session

class LoginWidget(QWidget):
    login_successful = pyqtSignal(int, str)  # 发送用户ID和用户名
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 添加标题
        title = QLabel("Secure Chat Login")
        title.setStyleSheet("font-size: 24px; margin-bottom: 20px;")
        layout.addWidget(title)
        
        # 用户名输入
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)
        
        # 密码输入
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)
        
        # 登录按钮
        login_button = QPushButton("Login")
        login_button.clicked.connect(self.handle_login)
        layout.addWidget(login_button)
        
        # 注册按钮
        register_button = QPushButton("Register")
        register_button.clicked.connect(self.handle_register)
        layout.addWidget(register_button)
        
        # 添加一些空间
        layout.addStretch()
    
    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter both username and password")
            return
        
        try:
            # 检查用户是否存在
            user = verify_user(username, password)
            if user:
                # 初始化用户专属数据库
                init_database(user['id'])
                self.login_successful.emit(user['id'], username)  # 发送用户名
            else:
                QMessageBox.warning(self, "Login Failed", "Invalid username or password")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Login failed: {str(e)}")
    
    def handle_register(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter both username and password")
            return
        
        try:
            # 注册新用户
            user = register_user(username, password)
            # 初始化用户专属数据库
            init_database(user.id)
            QMessageBox.information(self, "Success", f"Registration successful! Your user ID is: {user.id}")
            self.login_successful.emit(user.id, username)  # 发送用户名
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Registration failed: {str(e)}") 
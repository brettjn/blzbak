"""
Graphical installer for blzbakd daemon using Qt6.

This installer provides a step-by-step wizard to install and configure
the blzbak backup daemon on Ubuntu 24.04.
"""

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QCheckBox,
    QTextEdit, QProgressBar, QMessageBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

# Handle both relative and absolute imports
try:
    from .system_ops import (
        create_blzbak_user, install_systemd_service, start_daemon,
        check_root_privileges, stop_daemon, daemon_is_running
    )
    from .file_ops import (
        find_blzbak_zip, extract_blzbak_zip, install_daemon_files,
        create_daemon_config, cleanup_temp_files
    )
except ImportError:
    # If relative imports fail, try absolute imports
    from system_ops import (
        create_blzbak_user, install_systemd_service, start_daemon,
        check_root_privileges, stop_daemon, daemon_is_running
    )
    from file_ops import (
        find_blzbak_zip, extract_blzbak_zip, install_daemon_files,
        create_daemon_config, cleanup_temp_files
    )


class IntroPage(QWizardPage):
    """Welcome page for the installer."""
    
    def __init__(self):
        super().__init__()
        self.setTitle("Welcome to blzbak Daemon Installer")
        self.setSubTitle(
            "This wizard will guide you through the installation of the "
            "blzbak backup daemon (blzbakd) on your system."
        )
        
        layout = QVBoxLayout()
        
        # Welcome message
        welcome = QLabel(
            "blzbakd is a server-side backup daemon that works with the "
            "blzbak backup client.\n\n"
            "The installer will:\n"
            "• Extract and install the daemon\n"
            "• Create a dedicated system user and group\n"
            "• Configure storage locations\n"
            "• Set up automatic startup (systemd service)\n\n"
            "You will need administrator privileges to complete this installation."
        )
        welcome.setWordWrap(True)
        layout.addWidget(welcome)
        
        # Check for zip file
        self.zip_status = QLabel()
        layout.addWidget(self.zip_status)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def initializePage(self):
        """Check for blzbak zip file when page is shown."""
        zip_file = find_blzbak_zip()
        if zip_file:
            self.zip_status.setText(f"✓ Found: {zip_file.name}")
            self.zip_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.zip_status.setText(
                "✗ Error: blzbak.zip not found in installer directory"
            )
            self.zip_status.setStyleSheet("color: red; font-weight: bold;")
    
    def validatePage(self):
        """Check if we can proceed."""
        if not check_root_privileges():
            QMessageBox.warning(
                self,
                "Insufficient Privileges",
                "This installer requires administrator (root) privileges.\n\n"
                "Please run the installer with sudo:\n"
                "sudo python3 installer_gui.py"
            )
            return False
        
        zip_file = find_blzbak_zip()
        if not zip_file:
            QMessageBox.critical(
                self,
                "Missing Package",
                "Could not find blzbak.zip in the installer directory.\n"
                "Please ensure the package file is present."
            )
            return False
        
        return True


class PathConfigPage(QWizardPage):
    """Page to configure installation paths."""
    
    def __init__(self):
        super().__init__()
        self.setTitle("Installation Paths")
        self.setSubTitle("Choose where to install blzbakd and store backups.")
        
        layout = QVBoxLayout()
        
        # Installation path group
        install_group = QGroupBox("Daemon Installation")
        install_layout = QVBoxLayout()
        install_layout.setSpacing(10)
        
        # Install location row
        install_form = QFormLayout()
        self.install_path_edit = QLineEdit("/opt/blzbak")
        self.install_path_edit.setMinimumWidth(400)
        self.install_path_edit.setMinimumHeight(28)
        install_path_btn = QPushButton("Browse...")
        install_path_btn.clicked.connect(self.browse_install_path)
        
        install_path_layout = QHBoxLayout()
        install_path_layout.addWidget(self.install_path_edit)
        install_path_layout.addWidget(install_path_btn)
        
        install_form.addRow("Install Location:", install_path_layout)
        install_layout.addLayout(install_form)
        
        # Description label with indent
        desc_label = QLabel("Directory where the daemon will be installed")
        desc_label.setStyleSheet("color: gray; font-size: 9pt; margin-left: 20px;")
        install_layout.addWidget(desc_label)
        
        install_group.setLayout(install_layout)
        layout.addWidget(install_group)
        
        # Backup storage group
        storage_group = QGroupBox("Backup Storage")
        storage_layout = QVBoxLayout()
        storage_layout.setSpacing(10)
        
        # Base path row - use HBox instead of FormLayout for better control
        base_row = QHBoxLayout()
        base_label = QLabel("Backup Directory:")
        base_label.setMinimumWidth(120)
        base_label.setMinimumHeight(28)
        base_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        base_row.addWidget(base_label)
        
        self.base_path_edit = QLineEdit("/blzbak")
        self.base_path_edit.setMinimumWidth(400)
        self.base_path_edit.setMinimumHeight(28)
        base_row.addWidget(self.base_path_edit)
        
        base_path_btn = QPushButton("Browse...")
        base_path_btn.setMinimumHeight(28)
        base_path_btn.clicked.connect(self.browse_base_path)
        base_row.addWidget(base_path_btn)
        
        storage_layout.addLayout(base_row)
        
        # Description with proper spacing
        base_desc = QLabel("Root directory for storing backups")
        base_desc.setStyleSheet("color: gray; font-size: 9pt; padding-left: 130px;")
        base_desc.setMinimumHeight(20)
        storage_layout.addWidget(base_desc)
        
        # Add spacing between fields
        storage_layout.addSpacing(10)
        
        # Diffs path row - use HBox instead of FormLayout for better control
        diff_row = QHBoxLayout()
        diff_label = QLabel("Diffs Directory:")
        diff_label.setMinimumWidth(120)
        diff_label.setMinimumHeight(28)
        diff_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        diff_row.addWidget(diff_label)
        
        self.diff_path_edit = QLineEdit("/blzbak/diffs")
        self.diff_path_edit.setMinimumWidth(400)
        self.diff_path_edit.setMinimumHeight(28)
        diff_row.addWidget(self.diff_path_edit)
        
        diff_path_btn = QPushButton("Browse...")
        diff_path_btn.setMinimumHeight(28)
        diff_path_btn.clicked.connect(self.browse_diff_path)
        diff_row.addWidget(diff_path_btn)
        
        storage_layout.addLayout(diff_row)
        
        # Description with proper spacing
        diff_desc = QLabel("Directory for storing differential archives")
        diff_desc.setStyleSheet("color: gray; font-size: 9pt; padding-left: 130px;")
        diff_desc.setMinimumHeight(20)
        storage_layout.addWidget(diff_desc)
        
        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)
        
        # Network configuration
        network_group = QGroupBox("Network Configuration")
        network_layout = QVBoxLayout()
        network_layout.setSpacing(10)
        
        # Port and bind address
        network_form = QFormLayout()
        self.port_edit = QLineEdit("7890")
        self.port_edit.setMinimumHeight(28)
        network_form.addRow("TCP Port:", self.port_edit)
        
        self.host_edit = QLineEdit("0.0.0.0")
        self.host_edit.setMinimumHeight(28)
        network_form.addRow("Bind Address:", self.host_edit)
        network_layout.addLayout(network_form)
        
        # Description
        network_desc = QLabel("0.0.0.0 = all interfaces, 127.0.0.1 = localhost only")
        network_desc.setStyleSheet("color: gray; font-size: 9pt; margin-left: 20px;")
        network_layout.addWidget(network_desc)
        
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # Register fields for the wizard
        self.registerField("install_path*", self.install_path_edit)
        self.registerField("base_path*", self.base_path_edit)
        self.registerField("diff_path*", self.diff_path_edit)
        self.registerField("port", self.port_edit)
        self.registerField("host", self.host_edit)
        
        # Update diff path when base path changes
        self.base_path_edit.textChanged.connect(self.update_diff_path)
    
    def initializePage(self):
        """Trigger completion check when page is shown."""
        # Emit completeChanged to update wizard button states
        # This ensures the Next button is enabled when fields have default values
        self.completeChanged.emit()
    
    def browse_install_path(self):
        """Open directory browser for installation path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Installation Directory", self.install_path_edit.text()
        )
        if path:
            self.install_path_edit.setText(path)
    
    def browse_base_path(self):
        """Open directory browser for backup base path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Backup Directory", self.base_path_edit.text()
        )
        if path:
            self.base_path_edit.setText(path)
    
    def browse_diff_path(self):
        """Open directory browser for diff path."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Diffs Directory", self.diff_path_edit.text()
        )
        if path:
            self.diff_path_edit.setText(path)
    
    def update_diff_path(self, base_path):
        """Auto-update diff path when base path changes."""
        if self.diff_path_edit.text() == "" or \
           self.diff_path_edit.text().startswith(base_path.rsplit('/', 1)[0]):
            self.diff_path_edit.setText(f"{base_path}/diffs")
    
    def validatePage(self):
        """Validate the paths."""
        install_path = self.install_path_edit.text()
        base_path = self.base_path_edit.text()
        diff_path = self.diff_path_edit.text()
        port = self.port_edit.text()
        
        # Validate port
        try:
            port_num = int(port)
            if not (1 <= port_num <= 65535):
                raise ValueError()
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Port", "Port must be a number between 1 and 65535."
            )
            return False
        
        # Check if paths are absolute
        if not Path(install_path).is_absolute():
            QMessageBox.warning(
                self, "Invalid Path", "Installation path must be absolute."
            )
            return False
        
        if not Path(base_path).is_absolute():
            QMessageBox.warning(
                self, "Invalid Path", "Backup directory must be absolute."
            )
            return False
        
        return True


class InstallationWorker(QThread):
    """Worker thread for performing installation tasks."""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
    
    def run(self):
        """Perform the installation."""
        try:
            # Step 1: Find and extract zip
            self.progress.emit(10, "Finding blzbak package...")
            zip_file = find_blzbak_zip()
            if not zip_file:
                self.finished.emit(False, "Could not find blzbak.zip")
                return
            
            self.progress.emit(20, "Extracting package...")
            temp_dir = extract_blzbak_zip(zip_file)
            if not temp_dir:
                self.finished.emit(False, "Failed to extract package")
                return
            
            # Step 2: Create user and group
            self.progress.emit(30, "Creating blzbak user and group...")
            if not create_blzbak_user():
                cleanup_temp_files(temp_dir)
                self.finished.emit(False, "Failed to create system user")
                return
            
            # Step 3: Install daemon files
            self.progress.emit(50, "Installing daemon files...")
            if not install_daemon_files(temp_dir, self.config['install_path']):
                cleanup_temp_files(temp_dir)
                self.finished.emit(False, "Failed to install daemon files")
                return
            
            # Step 4: Create configuration
            self.progress.emit(60, "Creating configuration...")
            if not create_daemon_config(self.config):
                cleanup_temp_files(temp_dir)
                self.finished.emit(False, "Failed to create configuration")
                return
            
            # Step 5: Create storage directories
            self.progress.emit(70, "Creating storage directories...")
            try:
                Path(self.config['base_path']).mkdir(parents=True, exist_ok=True)
                Path(self.config['diff_path']).mkdir(parents=True, exist_ok=True)
                
                # Set ownership
                os.system(
                    f"chown -R blzbak:blzbak {self.config['base_path']} "
                    f"{self.config['diff_path']}"
                )
            except Exception as e:
                cleanup_temp_files(temp_dir)
                self.finished.emit(False, f"Failed to create directories: {e}")
                return
            
            # Step 6: Install systemd service
            self.progress.emit(80, "Installing systemd service...")
            if not install_systemd_service(self.config):
                cleanup_temp_files(temp_dir)
                self.finished.emit(False, "Failed to install systemd service")
                return
            
            # Step 7: Cleanup
            self.progress.emit(90, "Cleaning up...")
            cleanup_temp_files(temp_dir)
            
            self.progress.emit(100, "Installation complete!")
            self.finished.emit(True, "Installation completed successfully")
            
        except Exception as e:
            self.finished.emit(False, f"Unexpected error: {e}")


class InstallationPage(QWizardPage):
    """Page showing installation progress."""
    
    def __init__(self):
        super().__init__()
        self.setTitle("Installing blzbakd")
        self.setSubTitle("Please wait while the daemon is being installed...")
        self.setCommitPage(True)
        
        layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Initializing...")
        layout.addWidget(self.status_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        layout.addWidget(self.log_text)
        
        layout.addStretch()
        self.setLayout(layout)
        
        self.worker = None
        self.install_success = False
    
    def initializePage(self):
        """Start the installation when page is shown."""
        # Gather configuration
        config = {
            'install_path': self.field('install_path'),
            'base_path': self.field('base_path'),
            'diff_path': self.field('diff_path'),
            'port': self.field('port'),
            'host': self.field('host'),
        }
        
        # Start worker thread
        self.worker = InstallationWorker(config)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.installation_finished)
        self.worker.start()
        
        # Disable back/cancel during installation
        self.wizard().button(QWizard.WizardButton.BackButton).setEnabled(False)
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(False)
    
    def update_progress(self, value, message):
        """Update progress bar and status."""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self.log_text.append(f"[{value}%] {message}")
    
    def installation_finished(self, success, message):
        """Handle installation completion."""
        self.install_success = success
        
        if success:
            self.status_label.setText("✓ " + message)
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("✗ " + message)
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Installation Failed", message)
        
        self.log_text.append(f"\n{'='*50}\n{message}")
        
        # Re-enable navigation
        self.wizard().button(QWizard.WizardButton.BackButton).setEnabled(not success)
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(True)
        
        # Allow proceeding to next page only if successful
        self.setFinalPage(False)
        self.completeChanged.emit()
    
    def isComplete(self):
        """Page is complete when installation finishes successfully."""
        return self.install_success
    
    def validatePage(self):
        """Wait for worker to finish before proceeding."""
        if self.worker and self.worker.isRunning():
            return False
        return self.install_success


class CompletionPage(QWizardPage):
    """Final page with option to start daemon."""
    
    def __init__(self):
        super().__init__()
        self.setTitle("Installation Complete")
        self.setSubTitle("blzbakd has been successfully installed!")
        self.setFinalPage(True)
        
        layout = QVBoxLayout()
        
        success_msg = QLabel(
            "The blzbak daemon has been installed and configured.\n\n"
            "The daemon has been set up to start automatically at boot time."
        )
        success_msg.setWordWrap(True)
        layout.addWidget(success_msg)
        
        self.start_now_checkbox = QCheckBox("Start the daemon now")
        self.start_now_checkbox.setChecked(True)
        layout.addWidget(self.start_now_checkbox)
        
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        info_label = QLabel(
            "\n<b>Next steps:</b>\n"
            "• Configure backup clients to connect to this server\n"
            "• Check daemon status: sudo systemctl status blzbakd\n"
            "• View logs: sudo journalctl -u blzbakd -f\n"
            "• Stop daemon: sudo systemctl stop blzbakd\n"
            "• Restart daemon: sudo systemctl restart blzbakd"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.setLayout(layout)
    
    def initializePage(self):
        """Check if daemon is already running."""
        if daemon_is_running():
            self.status_label.setText(
                "Note: A blzbakd daemon is already running."
            )
            self.status_label.setStyleSheet("color: orange;")
            self.start_now_checkbox.setChecked(False)
            self.start_now_checkbox.setText("Restart the daemon now")
    
    def validatePage(self):
        """Start daemon if requested."""
        if self.start_now_checkbox.isChecked():
            self.status_label.setText("Starting daemon...")
            QApplication.processEvents()
            
            # Stop if already running
            if daemon_is_running():
                stop_daemon()
            
            # Start daemon
            success, message = start_daemon()
            
            if success:
                self.status_label.setText("✓ Daemon started successfully")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.status_label.setText(f"✗ Failed to start daemon: {message}")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                QMessageBox.warning(
                    self, "Daemon Start Failed",
                    f"Could not start the daemon:\n{message}\n\n"
                    "You can start it manually with:\nsudo systemctl start blzbakd"
                )
        
        return True


class InstallerWizard(QWizard):
    """Main installer wizard."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("blzbak Daemon Installer")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setFixedSize(700, 500)
        
        # Add pages
        self.addPage(IntroPage())
        self.addPage(PathConfigPage())
        self.addPage(InstallationPage())
        self.addPage(CompletionPage())
        
        # Set button text
        self.setButtonText(QWizard.WizardButton.FinishButton, "Close")


def main():
    """Main entry point for the installer."""
    app = QApplication(sys.argv)
    app.setApplicationName("blzbak Installer")
    
    wizard = InstallerWizard()
    wizard.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

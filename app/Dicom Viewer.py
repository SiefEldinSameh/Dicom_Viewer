import sys
import os
import logging
import traceback
from datetime import datetime
import numpy as np
import pydicom
import uuid
import random
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QTabWidget, QListWidget,
    QScrollArea, QWidget, QLineEdit, QHeaderView, QMessageBox, QGridLayout,
    QTextEdit, QProgressBar, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal,QTimer
from PyQt6.QtGui import QImage, QPixmap ,QIcon

# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DICOMWorker(QThread):
    """Thread for loading DICOM files asynchronously."""
    files_loaded = pyqtSignal(list)

    def __init__(self, directory):
        super().__init__()
        self.directory = directory

    def run(self):
        dicom_files = [
            os.path.join(root, file)
            for root, _, files in os.walk(self.directory)
            for file in files if file.lower().endswith('.dcm')
        ]
        self.files_loaded.emit(dicom_files)

class DICOMMetadataViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dicom_files = []
        self.current_file_index = 0
        self.current_dicom_data = None
        self.current_image_data = None  # Ensure this attribute exists


        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Enhanced DICOM Viewer')
        self.setGeometry(100, 100, 1300, 900)
        app_icon = QIcon("../assets/logo.png")
        self.setWindowIcon(app_icon)

        # Central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        # Top layout for buttons
        button_layout = QHBoxLayout()
        select_dir_btn = QPushButton('Select DICOM Directory')
        select_dir_btn.clicked.connect(self.select_dicom_directory)
        button_layout.addWidget(select_dir_btn)

        self.prev_btn = QPushButton('Previous')
        self.prev_btn.clicked.connect(self.show_previous_dicom)
        self.prev_btn.setEnabled(False)
        button_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton('Next')
        self.next_btn.clicked.connect(self.show_next_dicom)
        self.next_btn.setEnabled(False)
        button_layout.addWidget(self.next_btn)

        anonymize_all_btn = QPushButton('Anonymize All Files')
        anonymize_all_btn.clicked.connect(self.anonymize_all_dicom)
        button_layout.addWidget(anonymize_all_btn)

        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("Enter anonymization prefix")
        button_layout.addWidget(self.prefix_input)

        export_metadata_btn = QPushButton("Export Metadata")
        export_metadata_btn.clicked.connect(self.export_metadata)
        button_layout.addWidget(export_metadata_btn)

        main_layout.addLayout(button_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Main content layout
        content_layout = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.on_file_selected)
        content_layout.addWidget(self.file_list, 1)

        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget, 3)
        main_layout.addLayout(content_layout)

        # Metadata Tab
        metadata_tab = QWidget()
        metadata_layout = QVBoxLayout(metadata_tab)

        self.metadata_table = QTableWidget(0, 2)
        self.metadata_table.setHorizontalHeaderLabels(["Tag", "Value"])
        self.metadata_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        metadata_layout.addWidget(self.metadata_table)

        self.raw_metadata_text = QTextEdit()
        self.raw_metadata_text.setReadOnly(True)
        metadata_layout.addWidget(self.raw_metadata_text)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search DICOM tags...")
        search_layout.addWidget(self.search_input)

        search_btn = QPushButton('Search')
        search_btn.clicked.connect(self.search_metadata)
        search_layout.addWidget(search_btn)

        reset_btn = QPushButton('Reset')
        reset_btn.clicked.connect(self.reset_metadata_search)
        search_layout.addWidget(reset_btn)
        metadata_layout.addLayout(search_layout)

        self.add_group_display_buttons(metadata_layout)
        self.tab_widget.addTab(metadata_tab, "Metadata")

        # Image Tab
        self.image_tab = QWidget()
        self.image_layout = QVBoxLayout(self.image_tab)
        self.image_scroll_area = QScrollArea()
        self.image_grid = QGridLayout()
        grid_widget = QWidget()
        grid_widget.setLayout(self.image_grid)
        self.image_scroll_area.setWidgetResizable(True)
        self.image_scroll_area.setWidget(grid_widget)
        self.image_layout.addWidget(self.image_scroll_area)
        self.tab_widget.addTab(self.image_tab, "Images")
        # Brightness and Contrast sliders
        brightness_label = QLabel("Brightness:")
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(self.update_image_display)

        contrast_label = QLabel("Contrast:")
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(0, 200)
        self.contrast_slider.setValue(100)
        self.contrast_slider.valueChanged.connect(self.update_image_display)

        slider_layout = QVBoxLayout()
        slider_layout.addWidget(brightness_label)
        slider_layout.addWidget(self.brightness_slider)
        slider_layout.addWidget(contrast_label)
        slider_layout.addWidget(self.contrast_slider)

        self.image_layout.addLayout(slider_layout)
        cine_button_layout = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.start_cine_mode)
        cine_button_layout.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_cine_mode)
        self.stop_button.setEnabled(False)
        cine_button_layout.addWidget(self.stop_button)

        self.image_layout.addLayout(cine_button_layout)
        view_button_layout = QHBoxLayout()
        axial_button = QPushButton("Axial")
        axial_button.clicked.connect(lambda: self.switch_view('axial'))
        view_button_layout.addWidget(axial_button)

        coronal_button = QPushButton("Coronal")
        coronal_button.clicked.connect(lambda: self.switch_view('coronal'))
        view_button_layout.addWidget(coronal_button)

        sagittal_button = QPushButton("Sagittal")
        sagittal_button.clicked.connect(lambda: self.switch_view('sagittal'))
        view_button_layout.addWidget(sagittal_button)

        self.image_layout.addLayout(view_button_layout)




    def select_dicom_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select DICOM Directory")
        if dir_path:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.worker = DICOMWorker(dir_path)
            self.worker.files_loaded.connect(self.on_files_loaded)
            self.worker.start()

    def update_image_display(self):
        if not hasattr(self, 'original_image') or self.original_image is None:
            return

        # Get brightness and contrast values
        brightness = self.brightness_slider.value()
        contrast = self.contrast_slider.value() / 100.0

        # Create a copy of the original image
        adjusted_image = self.original_image.astype(np.float32)

        # Apply contrast
        mean = np.mean(adjusted_image)
        adjusted_image = mean + contrast * (adjusted_image - mean)

        # Apply brightness
        adjusted_image += brightness

        # Clip values to valid range
        adjusted_image = np.clip(adjusted_image, 0, 255).astype(np.uint8)

        # Create QImage
        height, width = adjusted_image.shape
        qimage = QImage(adjusted_image.data, width, height, width, QImage.Format.Format_Grayscale8)

        # Create label with the image
        label = QLabel()
        pixmap = QPixmap.fromImage(qimage)

        # Ensure current_zoom exists
        if not hasattr(self, 'current_zoom'):
            self.current_zoom = 1.0

        # Scale the image based on current zoom WITHOUT changing the container
        scaled_pixmap = pixmap.scaled(
            int(width * self.current_zoom),
            int(height * self.current_zoom),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # Create a scroll area to enable zooming within the image
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # Create a label to hold the scaled image
        zoom_label = QLabel()
        zoom_label.setPixmap(scaled_pixmap)
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set the zoomed label in the scroll area
        scroll_area.setWidget(zoom_label)

        # Create zoom buttons
        zoom_in_button = QPushButton("Zoom In")
        zoom_in_button.clicked.connect(self.zoom_in)

        zoom_out_button = QPushButton("Zoom Out")
        zoom_out_button.clicked.connect(self.zoom_out)

        # Layout for image and zoom buttons
        layout = QVBoxLayout()
        layout.addWidget(scroll_area)

        zoom_button_layout = QHBoxLayout()
        zoom_button_layout.addWidget(zoom_in_button)
        zoom_button_layout.addWidget(zoom_out_button)

        layout.addLayout(zoom_button_layout)

        # Clear previous grid contents
        for i in reversed(range(self.image_grid.count())):
            widget = self.image_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Create a widget to hold the layout
        widget = QWidget()
        widget.setLayout(layout)

        # Add to grid
        self.image_grid.addWidget(widget, 0, 0)

    def zoom_in(self):
        """Zoom in on the image."""
        if not hasattr(self, 'current_zoom'):
            self.current_zoom = 1.0

        self.current_zoom *= 1.2  # Increase zoom by 20%
        self.update_image_display()

    def zoom_out(self):
        """Zoom out on the image."""
        if not hasattr(self, 'current_zoom'):
            self.current_zoom = 1.0

        self.current_zoom /= 1.2  # Decrease zoom by 20%

        # Prevent zooming out too far
        self.current_zoom = max(0.2, self.current_zoom)

        self.update_image_display()

    def on_files_loaded(self, dicom_files):
        self.progress_bar.setVisible(False)
        self.dicom_files = dicom_files
        self.file_list.clear()
        self.file_list.addItems([os.path.basename(f) for f in self.dicom_files])
        if self.dicom_files:
            self.display_dicom_file(self.dicom_files[0])
            self.next_btn.setEnabled(len(self.dicom_files) > 1)

    def on_file_selected(self, item):
        index = self.file_list.row(item)
        self.current_file_index = index
        self.display_dicom_file(self.dicom_files[index])

    def show_previous_dicom(self):
        if self.current_file_index > 0:
            self.current_file_index -= 1
            self.display_dicom_file(self.dicom_files[self.current_file_index])

    def show_next_dicom(self):
        if self.current_file_index < len(self.dicom_files) - 1:
            self.current_file_index += 1
            self.display_dicom_file(self.dicom_files[self.current_file_index])

    def display_dicom_file(self, file_path):
        try:
            dicom_data = pydicom.dcmread(file_path)
            self.current_dicom_data = dicom_data
            self.populate_metadata_table(dicom_data)
            self.visualize_dicom_images(dicom_data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def populate_metadata_table(self, dicom_data):
        self.metadata_table.setRowCount(0)
        for tag in dicom_data.dir():
            value = getattr(dicom_data, tag, 'N/A')
            row = self.metadata_table.rowCount()
            self.metadata_table.insertRow(row)
            self.metadata_table.setItem(row, 0, QTableWidgetItem(tag))
            self.metadata_table.setItem(row, 1, QTableWidgetItem(str(value)))

    # Additional methods (search, reset, anonymize, export, visualize, etc.) continue here...
    def search_metadata(self):
        search_term = self.search_input.text().lower().strip()
        for row in range(self.metadata_table.rowCount()):
            is_visible = False
            for col in range(2):
                item = self.metadata_table.item(row, col)
                if item and search_term in item.text().lower():
                    is_visible = True
                    break
            self.metadata_table.setRowHidden(row, not is_visible)

    def reset_metadata_search(self):
        self.search_input.clear()
        for row in range(self.metadata_table.rowCount()):
            self.metadata_table.setRowHidden(row, False)

    def anonymize_all_dicom(self):
        prefix = self.prefix_input.text().strip()
        if not prefix:
            QMessageBox.warning(self, "Invalid Input", "Please enter a prefix for anonymization.")
            return
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        for idx, file_path in enumerate(self.dicom_files):
            try:
                dicom_data = pydicom.dcmread(file_path)
                self.anonymize_dicom_data(dicom_data, prefix)
                anonymized_filename = os.path.join(output_dir, f"ANON_{os.path.basename(file_path)}")
                dicom_data.save_as(anonymized_filename)
                logging.info(f"Anonymized and saved: {anonymized_filename}")
            except Exception as e:
                logging.error(f"Failed to anonymize {file_path}: {e}")

            self.progress_bar.setValue(int((idx + 1) / len(self.dicom_files) * 100))

        QMessageBox.information(self, "Success", "All files anonymized successfully!")
        self.progress_bar.setVisible(False)

    import uuid
    import random
    from datetime import datetime, timedelta

    def anonymize_dicom_data(self, dicom_data, prefix):

        identifier_replacements = {
            'PatientName': f"{prefix}_Patient_{uuid.uuid4().hex[:8]}",
            'PatientID': f"{prefix}_ID_{uuid.uuid4().hex[:8]}",
            'PatientAddress': f"{prefix}_Anonymous_Address",
            'ReferringPhysicianName': f"{prefix}_Dr_Anonymous",
            'InstitutionName': f"{prefix}_Anonymous_Institution"
        }

        # Fields to clear
        fields_to_clear = [
            'PatientTelephoneNumbers', 'PatientEmailAddresses',
            'OtherPatientIDs', 'OtherPatientNames', 'PatientComments'
        ]

        # Fields for date shifting
        date_fields = ['PatientBirthDate', 'StudyDate', 'SeriesDate', 'AcquisitionDate', 'ContentDate']

        # Replace identifiers with prefixed random values
        for tag, replacement in identifier_replacements.items():
            if hasattr(dicom_data, tag):
                setattr(dicom_data, tag, replacement)

        # Clear optional sensitive fields
        for tag in fields_to_clear:
            if hasattr(dicom_data, tag):
                setattr(dicom_data, tag, '')

        # Shift dates by a random number of days, with prefix included
        date_shift = random.randint(-365, 365)  # Random shift within one year
        for date_tag in date_fields:
            if hasattr(dicom_data, date_tag) and getattr(dicom_data, date_tag):
                original_date = getattr(dicom_data, date_tag)
                try:
                    shifted_date = self.shift_date_with_prefix(original_date, date_shift, prefix)
                    setattr(dicom_data, date_tag, shifted_date)
                except ValueError:
                    logging.warning(f"Invalid date format for {date_tag}: {original_date}")

        # Anonymize UIDs with prefix
        uid_fields = ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID']
        for uid_field in uid_fields:
            if hasattr(dicom_data, uid_field):
                setattr(dicom_data, uid_field, f"{prefix}_{uuid.uuid4().urn}")

        logging.info("Anonymization with prefixed IDs and date shifting complete.")

    @staticmethod
    def shift_date_with_prefix(original_date, days_shift, prefix):
        """
        Shifts a DICOM date by a given number of days and adds a prefix.

        :param original_date: Original date as a string in 'YYYYMMDD' format.
        :param days_shift: Number of days to shift the date.
        :param prefix: The prefix to include in the shifted date.
        :return: Shifted date as a string in 'YYYYMMDD_Prefix' format.
        """
        try:
            date_obj = datetime.strptime(original_date, "%Y%m%d")
            shifted_date = date_obj + timedelta(days=days_shift)
            return f"{shifted_date.strftime('%Y%m%d')}_{prefix}"
        except ValueError:
            raise ValueError(f"Invalid date format: {original_date}")

    def add_group_display_buttons(self, layout):
        # Predefined groups
        groups = ['Patient', 'Study', 'Modality', 'Physician', 'Image']
        for group in groups:
            btn = QPushButton(f"Show {group} Elements")
            btn.clicked.connect(lambda checked, g=group: self.show_group_elements(g))
            layout.addWidget(btn)

        # Custom group input
        custom_group_layout = QHBoxLayout()
        self.custom_group_input = QLineEdit()
        self.custom_group_input.setPlaceholderText("Enter group number (hex)")
        custom_group_layout.addWidget(self.custom_group_input)

        custom_group_btn = QPushButton("Show Custom Group")
        custom_group_btn.clicked.connect(self.show_custom_group)
        custom_group_layout.addWidget(custom_group_btn)

        layout.addLayout(custom_group_layout)

    def show_group_elements(self, group):
        if not self.current_dicom_data:
            QMessageBox.warning(self, "No File", "No DICOM file selected.")
            return

        elements = self.get_group_elements(group, self.current_dicom_data)
        if elements:
            # Format the output with consistent spacing
            formatted_output = []
            max_key_length = max(len(str(k)) for k in elements.keys())
            for k, v in elements.items():
                formatted_output.append(f"{str(k):<{max_key_length}} : {v}")
            self.raw_metadata_text.setText("\n".join(formatted_output))
        else:
            self.raw_metadata_text.setText(f"No elements found for group {group}")

    def show_custom_group(self):
        group_text = self.custom_group_input.text().strip()
        if not group_text:
            QMessageBox.warning(self, "Invalid Input", "Please enter a group number")
            return

        try:
            # Handle both decimal and hexadecimal input
            if group_text.startswith('0x'):
                group_number = int(group_text, 16)
            else:
                group_number = int(group_text, 16 if any(c in 'abcdefABCDEF' for c in group_text) else 10)
            self.show_group_elements(group_number)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid hexadecimal or decimal number")

    def get_group_elements(self, group, dicom_data):

        # Predefined groups mapping
        group_mappings = {
            'Patient': 0x0010,
            'Study': 0x0008,
            'Series': 0x0020,
            'Image': 0x0028,
            'Equipment': 0x0018,
            'Modality': 0x0008,  # Modality is typically in Study group
            'Physician': 0x0032  # Physician information
        }

        elements = {}

        try:
            # Convert string group names to their corresponding numbers
            if isinstance(group, str) and group in group_mappings:
                group_number = group_mappings[group]
            elif isinstance(group, (int, str)):
                # If it's already a number or hex string, convert to int
                group_number = int(str(group), 16) if isinstance(group, str) else group
            else:
                logging.error(f"Invalid group identifier: {group}")
                return elements

            # Iterate through all elements in the DICOM dataset
            for elem in dicom_data:
                tag_group = elem.tag.group

                # If this element belongs to the requested group
                if tag_group == group_number:
                    try:
                        # Get element name if available, otherwise use tag string
                        name = elem.name if hasattr(elem, 'name') else f"({elem.tag.group:04x},{elem.tag.element:04x})"

                        # Handle different types of values
                        if elem.VR == "SQ":
                            value = "Sequence"
                        elif elem.VR == "UN":
                            value = "Unknown"
                        elif elem.VR in ["OB", "OW"]:
                            value = f"Binary data of length {len(elem.value)}"
                        else:
                            value = elem.value

                        elements[name] = str(value)
                    except Exception as e:
                        logging.warning(f"Error processing element {elem.tag}: {str(e)}")
                        elements[f"Tag-{elem.tag}"] = "Error reading value"

            # Add some helpful derived information for certain groups
            if isinstance(group, str):
                if group == 'Patient':
                    if 'PatientAge' not in elements and 'PatientBirthDate' in elements:
                        try:
                            birth_date = datetime.strptime(elements['PatientBirthDate'], "%Y%m%d")
                            study_date = datetime.strptime(getattr(dicom_data, 'StudyDate', '19700101'), "%Y%m%d")
                            age = study_date.year - birth_date.year
                            elements['Calculated PatientAge'] = f"{age}Y"
                        except:
                            pass
                elif group == 'Image':
                    if 'PixelSpacing' in elements:
                        elements['Image Size'] = f"{dicom_data.Rows}x{dicom_data.Columns} pixels"
                        try:
                            spacing = dicom_data.PixelSpacing
                            elements['Pixel Spacing'] = f"{spacing[0]}mm x {spacing[1]}mm"
                        except:
                            pass

        except Exception as e:
            logging.error(f"Error processing group {group}: {str(e)}")
            return {'Error': f"Failed to process group: {str(e)}"}

        return elements

    def get_available_groups(self):
        if not self.current_dicom_data:
            return []

        groups = set()
        for elem in self.current_dicom_data:
            groups.add(elem.tag.group)
        return sorted(list(groups))

    def export_metadata(self):
        if not self.current_dicom_data:
            QMessageBox.warning(self, "No File", "No DICOM file selected.")
            return

        export_file_path, _ = QFileDialog.getSaveFileName(self, "Export Metadata", "", "CSV Files (*.csv)")
        if not export_file_path:
            return

        try:
            with open(export_file_path, 'w') as f:
                for row in range(self.metadata_table.rowCount()):
                    tag = self.metadata_table.item(row, 0).text()
                    value = self.metadata_table.item(row, 1).text()
                    f.write(f"{tag},{value}\n")
            QMessageBox.information(self, "Success", "Metadata exported successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export metadata: {e}")

    def switch_view(self, view_type):
        """Switch between axial, coronal, and sagittal views."""
        if not hasattr(self, 'original_image_data') or self.original_image_data is None:
            QMessageBox.warning(self, "No Image", "No 3D image data available.")
            return

        try:
            if view_type == 'axial':
                self.current_image_data = self.original_image_data
            elif view_type == 'coronal':
                self.current_image_data = np.transpose(self.original_image_data, (1, 0, 2))
            elif view_type == 'sagittal':
                self.current_image_data = np.transpose(self.original_image_data, (2, 0, 1))
            else:
                QMessageBox.warning(self, "Invalid View", "Invalid plane specified.")
                return

            # Update the display with the new orientation
            self.display_m2d_images(self.current_image_data)
        except Exception as e:
            QMessageBox.warning(self, "View Switch Error", f"Could not switch view: {str(e)}")

    def visualize_dicom_images(self, dicom_data):
        """Load and visualize DICOM image data."""
        for i in reversed(range(self.image_grid.count())):
            widget = self.image_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            if hasattr(dicom_data, 'pixel_array'):
                pixel_data = dicom_data.pixel_array

                normalized_data = self.normalize_image(pixel_data)

                if normalized_data.ndim == 2:
                    self.current_image_data = normalized_data
                    self.display_single_image(normalized_data)
                elif normalized_data.ndim == 3:
                    if normalized_data.shape[0] < max(normalized_data.shape[1:]):
                        # Likely a 3D image with multiple slices
                        self.original_image_data = normalized_data  # Store original 3D data
                        self.current_image_data = normalized_data
                        self.display_m2d_images(normalized_data)
                    else:
                        # Likely an M2D image (video/cine)
                        self.display_m2d_images_as_video(normalized_data)
                elif normalized_data.ndim == 4:
                    # 4D image (multiple series of 3D images)
                    self.display_m2d_images_as_video(normalized_data)

                else:
                    QMessageBox.warning(self, "Unsupported Image", "Unsupported image dimensions.")
            else:
                QMessageBox.warning(self, "No Image Data", "Selected DICOM file contains no image data.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to display image: {str(e)}")

    def enable_tile_navigation(self, enable):
        """Dynamically show or hide tile navigation buttons."""
        if not hasattr(self, 'tile_navigation_buttons'):
            self.tile_navigation_buttons = QHBoxLayout()
            self.tile_previous_btn = QPushButton("Previous 7 Tiles")
            self.tile_previous_btn.clicked.connect(self.show_previous_tile_set)
            self.tile_navigation_buttons.addWidget(self.tile_previous_btn)

            self.tile_next_btn = QPushButton("Next 7 Tiles")
            self.tile_next_btn.clicked.connect(self.show_next_tile_set)
            self.tile_navigation_buttons.addWidget(self.tile_next_btn)

            self.image_layout.addLayout(self.tile_navigation_buttons)

        self.tile_previous_btn.setVisible(enable)
        self.tile_next_btn.setVisible(enable)

    def show_previous_tile(self):
        if hasattr(self, 'current_tile_index') and self.current_tile_index > 0:
            self.current_tile_index -= 1
            self.display_single_image(self.current_image_data[self.current_tile_index])

    def show_next_tile(self):
        if hasattr(self, 'current_tile_index') and self.current_tile_index < self.current_image_data.shape[0] - 1:
            self.current_tile_index += 1
            self.display_single_image(self.current_image_data[self.current_tile_index])

    def display_single_image(self, image_data):
        # Ensure image is uint8
        if image_data.dtype != np.uint8:
            image_data = (image_data - image_data.min()) / (image_data.max() - image_data.min()) * 255
            image_data = image_data.astype(np.uint8)

        # Store the original image for manipulation
        self.original_image = image_data.copy()

        # Reset zoom
        self.current_zoom = 1.0

        # Create the initial display
        self.update_image_display()

    def display_m2d_images(self, image_data):
        """Display 3D images as tiles, 7 at a time."""
        self.current_tile_index = 0  # Start at the first tile
        self.current_image_data = image_data  # Store the 3D image data
        self.tiles_per_page = 7  # Number of tiles to display per page
        self.update_tiles()

    def update_tiles(self):
        """Update the displayed tiles based on the current tile index."""
        for i in reversed(range(self.image_grid.count())):
            widget = self.image_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        start_index = self.current_tile_index
        end_index = min(start_index + self.tiles_per_page, self.current_image_data.shape[0])

        for i in range(start_index, end_index):
            slice_data = self.current_image_data[i]
            normalized = self.normalize_image(slice_data)
            qimage = QImage(
                normalized.tobytes(),
                normalized.shape[1],
                normalized.shape[0],
                normalized.shape[1],
                QImage.Format.Format_Grayscale8
            )
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(qimage).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))
            row, col = divmod(i - start_index, 3)
            self.image_grid.addWidget(label, row, col)

        self.enable_tile_navigation(True)

    def play_images(self):
        """Automatically play through the slices of the current plane."""
        if not hasattr(self, 'current_image_data') or self.current_image_data is None:
            QMessageBox.warning(self, "No Image", "No 3D image data available.")
            return

        self.playing = True
        self.current_play_index = 0  # Start at the first slice

        def update_slice():
            if not self.playing or self.current_play_index >= self.current_image_data.shape[0]:
                self.playing = False
                self.timer.stop()
                return

            slice_data = self.current_image_data[self.current_play_index]
            normalized = self.normalize_image(slice_data)
            qimage = QImage(
                normalized.tobytes(),
                normalized.shape[1],
                normalized.shape[0],
                normalized.shape[1],
                QImage.Format.Format_Grayscale8
            )
            self.image_label.setPixmap(QPixmap.fromImage(qimage).scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio))
            self.current_play_index += 1

        self.timer = QTimer(self)
        self.timer.timeout.connect(update_slice)
        self.timer.start(100)  # Adjust the speed of playback as needed

    def show_next_tile_set(self):
        """Show the next set of tiles."""
        if self.current_tile_index + self.tiles_per_page < self.current_image_data.shape[0]:
            self.current_tile_index += self.tiles_per_page
            self.update_tiles()

    def show_previous_tile_set(self):
        """Show the previous set of tiles."""
        if self.current_tile_index > 0:
            self.current_tile_index -= self.tiles_per_page
            self.update_tiles()

    def display_m2d_images_as_video(self, image_data):
        """Display M2D images as a video (cine mode)."""
        # Validate the data shape
        if image_data.ndim not in (3, 4):
            QMessageBox.warning(self, "Invalid Data",
                                "M2D images must have 3D (time, height, width) or 4D (time, height, width, channels) shape.")
            logging.error(f"Invalid M2D image data shape: {image_data.shape}")
            return

        # Check all slices for validity
        for i, frame in enumerate(image_data):
            if frame.ndim < 2:
                logging.error(f"Invalid frame at index {i}: Shape: {frame.shape}")
                QMessageBox.warning(self, "Invalid Frame", f"Frame {i} has invalid shape {frame.shape}.")
                return

        self.cine_mode_active = True
        self.cine_index = 0
        self.current_image_data = image_data

        logging.info(f"Starting M2D cine mode. Image data shape: {image_data.shape}")

        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.cine_timer = QTimer(self)
        self.cine_timer.timeout.connect(self.cine_next_slice)
        self.cine_timer.start(100)  # Adjust playback speed

    def start_cine_mode(self):
        """Start cine mode playback."""
        if not hasattr(self, 'current_image_data') or self.current_image_data is None:
            QMessageBox.warning(self, "No Data", "No image data available for cine mode.")
            return

        if len(self.current_image_data.shape) < 3:
            QMessageBox.warning(self, "Invalid Data", "Cine mode requires multiple frames.")
            return

        self.cine_mode_active = True
        self.cine_index = 0  # Start from the first frame

        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.cine_timer = QTimer(self)
        self.cine_timer.timeout.connect(self.cine_next_slice)
        self.cine_timer.start(100)  # Set playback speed (100ms per frame)

    def cine_next_slice(self):
        """Display the next slice in cine mode."""
        if not self.cine_mode_active or self.current_image_data is None or self.cine_index >= \
                self.current_image_data.shape[0]:
            self.stop_cine_mode()
            return

        # Log the current slice
        current_slice = self.current_image_data[self.cine_index]
        logging.info(f"Displaying slice {self.cine_index}, shape: {current_slice.shape}")

        # Validate and display the current slice
        if current_slice.ndim == 2 or (current_slice.ndim == 3 and current_slice.shape[2] in [1, 3]):
            self.display_2d_image(current_slice)
        else:
            logging.error(f"Invalid slice at index {self.cine_index}: Shape: {current_slice.shape}")
            self.stop_cine_mode()
            return

        # Move to the next slice
        self.cine_index += 1

    def stop_cine_mode(self):
        """Stop cine mode playback."""
        if hasattr(self, 'cine_timer') and self.cine_timer.isActive():
            self.cine_timer.stop()

        self.cine_mode_active = False
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def display_2d_image(self, image_data):
        """Display a single 2D image (with enhanced quality)."""
        normalized = self.normalize_image(image_data)

        # Ensure the data is at least 2D
        if normalized.ndim < 2:
            QMessageBox.warning(self, "Image Error", "The image data is not 2D or valid for display.")
            logging.error(f"Image data shape invalid for display: {normalized.shape}")
            return

        # Convert to QImage
        if normalized.ndim == 2:  # Grayscale image
            qimage = QImage(normalized.tobytes(), normalized.shape[1], normalized.shape[0],
                            QImage.Format.Format_Grayscale8)
        elif normalized.ndim == 3 and normalized.shape[2] == 3:  # RGB image
            qimage = QImage(normalized.tobytes(), normalized.shape[1], normalized.shape[0],
                            normalized.shape[1] * 3, QImage.Format.Format_RGB888)
        else:
            QMessageBox.warning(self, "Image Error", "Unsupported image format.")
            logging.error(f"Unsupported image format: {normalized.shape}")
            return

        # Create a QPixmap from QImage
        pixmap = QPixmap.fromImage(qimage)

        # Add the image to the layout
        self.clear_image_grid()
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_grid.addWidget(label)

    def clear_image_grid(self):
        """Clear the image grid to show only the latest image."""
        for i in reversed(range(self.image_grid.count())):
            widget = self.image_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    @staticmethod
    @staticmethod
    @staticmethod
    @staticmethod
    def normalize_image(image):
        """Normalize the image for better contrast and display quality."""
        # Handle empty images
        if image.size == 0:
            logging.error("Image is empty. Skipping normalization.")
            return image

        # Normalize based on the last two dimensions (height, width)
        if image.ndim >= 2:
            image = image.astype(float)
            min_val = image.min()
            max_val = image.max()

            if max_val > min_val:
                image = (image - min_val) / (max_val - min_val) * 255
            else:
                logging.warning("Image has no range, likely constant value.")
                image.fill(0)

            return np.clip(image, 0, 255).astype(np.uint8)

        # Log and return for unsupported dimensions
        logging.error(f"Unsupported image dimensions for normalization: {image.shape}")
        return image

    def log_image_data_details(image_data):
        """Log details about the image data for debugging."""
        logging.info(f"Image data shape: {image_data.shape}")
        for i, frame in enumerate(image_data):
            if frame.ndim < 2:
                logging.error(f"Invalid frame at index {i}. Shape: {frame.shape}, Size: {frame.size}")
            else:
                logging.info(f"Valid frame at index {i}. Shape: {frame.shape}")


def exception_hook(exctype, value, tb):
    print(''.join(traceback.format_exception(exctype, value, tb)))
    sys.exit(1)

sys.excepthook = exception_hook


if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = DICOMMetadataViewer()
    viewer.show()
    sys.exit(app.exec())

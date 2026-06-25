(function () {
    'use strict';

    // Store files for each input field
    const fileStorage = {};

    /**
     * Preview multiple files with Odoo-style attachment display
     * @param {HTMLInputElement} input - The file input element
     * @param {string} previewId - The preview container ID
     */
    window.previewMultipleFiles = function(input, previewId) {
        const preview = document.getElementById(previewId);
        if (!preview) return;

        const inputId = input.id;
        
        // Initialize storage if not exists
        if (!fileStorage[inputId]) {
            fileStorage[inputId] = [];
        }
        
        // Append new files to existing ones (don't replace)
        const newFiles = Array.from(input.files);
        newFiles.forEach(newFile => {
            // Check if file with same name already exists
            const exists = fileStorage[inputId].some(existingFile => 
                existingFile.name === newFile.name && existingFile.size === newFile.size
            );
            
            // Only add if not duplicate
            if (!exists) {
                fileStorage[inputId].push(newFile);
            }
        });
        
        renderFilePreview(inputId, previewId);
    };

    /**
     * Render file preview with delete functionality
     * @param {string} inputId - The file input element ID
     * @param {string} previewId - The preview container ID
     */
    function renderFilePreview(inputId, previewId) {
        const preview = document.getElementById(previewId);
        const input = document.getElementById(inputId);
        
        if (!preview || !input) return;

        const files = fileStorage[inputId] || [];
        
        // Update the actual file input with all stored files
        updateFileInput(inputId);
        
        // Clear preview
        preview.innerHTML = '';

        if (files.length === 0) {
            preview.innerHTML = '<small class="text-muted">No files selected</small>';
            return;
        }

        // Display file count
        const fileCount = document.createElement('div');
        fileCount.className = 'mb-2';
        fileCount.innerHTML = `<small class="text-muted"><strong>${files.length}</strong> file(s) selected</small>`;
        preview.appendChild(fileCount);

        // Display each file
        files.forEach((file, index) => {
            const attachmentDiv = document.createElement('div');
            attachmentDiv.className = 'o_attachment o_attachment_many2many o_attachment_editable mb-2';
            attachmentDiv.setAttribute('title', file.name);
            
            // Determine file icon and extension
            let icon = 'fa-file-o';
            let ext = file.name.split('.').pop().toLowerCase();
            
            if (file.type.includes('pdf') || ext === 'pdf') {
                icon = 'fa-file-pdf-o text-danger';
            } else if (file.type.includes('image') || ['jpg', 'jpeg', 'png', 'gif', 'bmp'].includes(ext)) {
                icon = 'fa-file-image-o text-success';
            } else if (['doc', 'docx'].includes(ext)) {
                icon = 'fa-file-word-o text-primary';
            }

            const fileSize = formatFileSize(file.size);

            attachmentDiv.innerHTML = `
                <div class="o_attachment_wrap d-flex align-items-center p-2 border rounded bg-light">
                    <div class="o_image_box me-2">
                        <i class="fa ${icon} fa-2x"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="caption text-truncate" style="max-width: 300px;" title="${file.name}">
                            <strong>${file.name}</strong>
                        </div>
                        <div class="caption small text-muted">
                            <span class="text-uppercase"><b>${ext}</b></span> - ${fileSize}
                        </div>
                    </div>
                    <div class="o_attachment_uploaded">
                        <i class="fa fa-check text-success" title="Selected"></i>
                    </div>
                    <div class="o_attachment_delete" data-input-id="${inputId}" data-file-index="${index}">
                        <span role="img" aria-label="Delete" title="Delete">×</span>
                    </div>
                </div>
            `;

            preview.appendChild(attachmentDiv);
        });

        // Attach delete event listeners
        attachDeleteListeners(preview, inputId, previewId);
    }

    /**
     * Attach click event listeners to delete buttons
     * @param {HTMLElement} preview - The preview container
     * @param {string} inputId - The file input element ID
     * @param {string} previewId - The preview container ID
     */
    function attachDeleteListeners(preview, inputId, previewId) {
        const deleteButtons = preview.querySelectorAll('.o_attachment_delete');
        deleteButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const fileIndex = parseInt(this.getAttribute('data-file-index'));
                removeFile(inputId, fileIndex, previewId);
            });
        });
    }

    /**
     * Remove a file from storage and update input + preview
     * @param {string} inputId - The file input element ID
     * @param {number} fileIndex - Index of file to remove
     * @param {string} previewId - The preview container ID
     */
    function removeFile(inputId, fileIndex, previewId) {
        const input = document.getElementById(inputId);
        if (!input) return;

        // Remove file from storage
        if (fileStorage[inputId]) {
            fileStorage[inputId].splice(fileIndex, 1);
        }

        // Re-render preview (which will also update the file input)
        renderFilePreview(inputId, previewId);
    }

    /**
     * Update file input element with files from storage
     * @param {string} inputId - The file input element ID
     */
    function updateFileInput(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;

        const files = fileStorage[inputId] || [];
        
        // Create new DataTransfer to hold files
        const dataTransfer = new DataTransfer();
        files.forEach(file => {
            dataTransfer.items.add(file);
        });
        
        // Update input files
        input.files = dataTransfer.files;
    }

    /**
     * Format file size in human-readable format
     * @param {number} bytes - File size in bytes
     * @returns {string} Formatted file size
     */
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    /**
     * Clear file previews on form reset
     */
    function initFormReset() {
        const form = document.querySelector('form.s_website_form');
        if (form) {
            form.addEventListener('reset', function() {
                // Clear file storage
                Object.keys(fileStorage).forEach(key => {
                    fileStorage[key] = [];
                });
                
                // Clear all file previews
                document.querySelectorAll('[id$="_preview"]').forEach(preview => {
                    preview.innerHTML = '<small class="text-muted">No files selected</small>';
                });
                
                // Clear all file inputs
                document.querySelectorAll('input[type="file"]').forEach(input => {
                    input.value = '';
                });
            });
        }
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFormReset);
    } else {
        initFormReset();
    }

})();

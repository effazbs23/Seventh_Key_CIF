(function() {
    'use strict';

    function initResidencyStatusToggle() {
        const residentRadio = document.getElementById('resident_radio');
        const nonResidentRadio = document.getElementById('non_resident_radio');
        const emiratesIdInput = document.getElementById('emirates_id');
        const emiratesIdDocs = document.getElementById('emirates_id_docs');
        const residentAsterisks = document.querySelectorAll('.resident-required');
        
        if (!residentRadio || !nonResidentRadio) {
            return;
        }

        function updateFields() {
            if (residentRadio.checked) {
                // Resident: make EID required, show asterisks
                if (emiratesIdInput) {
                    emiratesIdInput.setAttribute('required', 'required');
                }
                // Don't set required attribute on file input (handled by custom validation)
                residentAsterisks.forEach(asterisk => {
                    asterisk.style.display = 'inline';
                });
            } else if (nonResidentRadio.checked) {
                // Non-resident: make EID optional, hide asterisks, clear EID docs
                if (emiratesIdInput) {
                    emiratesIdInput.removeAttribute('required');
                    emiratesIdInput.value = '';
                }
                if (emiratesIdDocs) {
                    emiratesIdDocs.value = '';
                }
                residentAsterisks.forEach(asterisk => {
                    asterisk.style.display = 'none';
                });
            }
        }

        residentRadio.addEventListener('change', updateFields);
        nonResidentRadio.addEventListener('change', updateFields);

        // Initialize
        updateFields();
    }

    function initResidencyDocumentsValidation() {
        const form = document.querySelector('form[action*="/cif/submit/"]');
        if (!form) return;

        // Important: the browser's native constraint validation can prevent the
        // form "submit" event from firing at all. To guarantee our file-upload
        // alerts show, validate on the submit-button click.
        const submitButtons = form.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]');
        if (!submitButtons.length) return;

        function focusUploadButtonFor(inputEl) {
            const formGroup = inputEl.closest('.form-group') || inputEl.closest('.residency_field');
            if (!formGroup) return;
            formGroup.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => {
                const uploadButton = formGroup.querySelector('.o_attach');
                if (uploadButton) {
                    uploadButton.focus();
                }
            }, 300);
        }

        function validateDocs(ev) {
            // Check if we're in change mode - documents are optional in change mode
            // because purchaser might only want to update personal info without changing documents
            const changeTokenInput = document.querySelector('input[name="change_token"]');
            const isChangeMode = changeTokenInput !== null;

            // Skip document validation in change mode
            if (isChangeMode) {
                return;
            }

            const residentRadio = document.getElementById('resident_radio');
            const passportDocs = document.getElementById('passport_docs');
            const emiratesIdDocs = document.getElementById('emirates_id_docs');

            // Emirates ID docs (required only for residents in new CIF mode)
            if (residentRadio && residentRadio.checked && emiratesIdDocs && (!emiratesIdDocs.files || emiratesIdDocs.files.length === 0)) {
                ev.preventDefault();
                ev.stopPropagation();
                alert('Emirates ID Supporting Document is required for residents. Please upload at least one file.');
                focusUploadButtonFor(emiratesIdDocs);
                return;
            }
            
            // Passport docs (required only in new CIF mode)
            if (passportDocs && (!passportDocs.files || passportDocs.files.length === 0)) {
                ev.preventDefault();
                ev.stopPropagation();
                alert('Passport Supporting Document is required. Please upload at least one file.');
                focusUploadButtonFor(passportDocs);
                return;
            }
        }

        submitButtons.forEach(btn => {
            btn.addEventListener('click', validateDocs);
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initResidencyStatusToggle();
            initResidencyDocumentsValidation();
        });
    } else {
        initResidencyStatusToggle();
        initResidencyDocumentsValidation();
    }
})();

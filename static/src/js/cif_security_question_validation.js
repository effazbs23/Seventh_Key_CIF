(function() {
    'use strict';

    // Function to update security question dropdowns
    function updateSecurityQuestions() {
        // Get all selected question IDs
        var selected1 = document.getElementById('security_question_1');
        var selected2 = document.getElementById('security_question_2');
        var selected3 = document.getElementById('security_question_3');
        
        if (!selected1 || !selected2 || !selected3) return;
        
        var selectedQuestions = [
            selected1.value,
            selected2.value,
            selected3.value
        ].filter(function(val) {
            return val !== '';
        });

        // Update each dropdown
        updateDropdown('security_question_1', selectedQuestions, selected1.value);
        updateDropdown('security_question_2', selectedQuestions, selected2.value);
        updateDropdown('security_question_3', selectedQuestions, selected3.value);

        // Update answer field maxlength and display
        updateAnswerMaxLength('security_question_1', 'security_answer_1', 'maxlength_1');
        updateAnswerMaxLength('security_question_2', 'security_answer_2', 'maxlength_2');
        updateAnswerMaxLength('security_question_3', 'security_answer_3', 'maxlength_3');
    }

    function updateDropdown(dropdownId, selectedQuestions, currentValue) {
        var dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;
        
        var options = dropdown.getElementsByTagName('option');
        
        for (var i = 0; i < options.length; i++) {
            var option = options[i];
            var optionValue = option.value;
            
            // Skip the empty option
            if (optionValue === '') continue;
            
            // Hide option if it's selected in another dropdown (but not this one)
            if (selectedQuestions.indexOf(optionValue) !== -1 && optionValue !== currentValue) {
                option.style.display = 'none';
                option.disabled = true;
            } else {
                option.style.display = '';
                option.disabled = false;
            }
        }
    }

    function updateAnswerMaxLength(questionId, answerId, maxLengthSpanId) {
        var questionSelect = document.getElementById(questionId);
        var answerInput = document.getElementById(answerId);
        var maxLengthSpan = document.getElementById(maxLengthSpanId);
        
        if (!questionSelect || !answerInput || !maxLengthSpan) return;
        
        var selectedOption = questionSelect.options[questionSelect.selectedIndex];
        var maxLength = selectedOption.getAttribute('data-maxlength') || '255';
        
        answerInput.setAttribute('maxlength', maxLength);
        maxLengthSpan.textContent = maxLength;
        
        // Clear answer if question changes
        if (answerInput.getAttribute('data-last-question') !== questionSelect.value) {
            answerInput.value = '';
            answerInput.setAttribute('data-last-question', questionSelect.value);
        }
    }

    function initSecurityQuestions() {
        // Attach change event listeners to all security question dropdowns
        var dropdown1 = document.getElementById('security_question_1');
        var dropdown2 = document.getElementById('security_question_2');
        var dropdown3 = document.getElementById('security_question_3');
        
        if (dropdown1) {
            dropdown1.addEventListener('change', updateSecurityQuestions);
        }
        if (dropdown2) {
            dropdown2.addEventListener('change', updateSecurityQuestions);
        }
        if (dropdown3) {
            dropdown3.addEventListener('change', updateSecurityQuestions);
        }
        
        // Initial update
        updateSecurityQuestions();
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSecurityQuestions);
    } else {
        initSecurityQuestions();
    }

})();

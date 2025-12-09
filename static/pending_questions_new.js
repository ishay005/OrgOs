async function loadPendingQuestions() {
    if (!currentUser || !currentUser.id) {
        console.error('No current user found');
        return;
    }
    
    const container = document.getElementById('pending-questions-container');
    container.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">Loading pending questions...</p>';
    
    try {
        const response = await fetch('/pending-questions', {
            headers: {
                'X-User-Id': currentUser.id
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load pending questions');
        }
        
        const pending = await response.json();
        
        if (pending.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 60px 20px;">
                    <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                    <h3 style="color: #2c5f2d; margin-bottom: 8px;">All Caught Up!</h3>
                    <p style="color: #666;">You have no pending questions. All your task attributes are up to date.</p>
                </div>
            `;
            return;
        }
        
        // Group by reason
        const grouped = {
            missing: pending.filter(p => p.reason === 'missing'),
            stale: pending.filter(p => p.reason === 'stale'),
            misaligned: pending.filter(p => p.reason === 'misaligned')
        };
        
        let html = `
            <div style="margin-bottom: 20px; padding: 16px; background: #f8f9fa; border-radius: 8px;">
                <h4 style="margin: 0 0 8px 0; color: #333;">Summary</h4>
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div style="padding: 8px 16px; background: #fff3cd; border-radius: 6px; border-left: 3px solid #ffc107;">
                        <strong>${grouped.missing.length}</strong> Missing
                    </div>
                    <div style="padding: 8px 16px; background: #cce5ff; border-radius: 6px; border-left: 3px solid #0066cc;">
                        <strong>${grouped.stale.length}</strong> Stale (>7 days)
                    </div>
                    <div style="padding: 8px 16px; background: #f8d7da; border-radius: 6px; border-left: 3px solid #dc3545;">
                        <strong>${grouped.misaligned.length}</strong> Misaligned
                    </div>
                </div>
            </div>
        `;
        
        // Display as a table with answer inputs
        html += `
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Priority</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Reason</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Task</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Attribute</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Your Answer</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">About</th>
                            <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const p of pending) {
            const reasonColor = p.reason === 'missing' ? '#ffc107' : 
                              p.reason === 'stale' ? '#0066cc' : '#dc3545';
            const reasonBadge = `<span style="display: inline-block; padding: 4px 8px; background: ${reasonColor}; color: white; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">${p.reason.toUpperCase()}</span>`;
            
            // Create appropriate input based on attribute type
            let inputHtml = '';
            if (p.attribute_type === 'enum' && p.allowed_values) {
                const options = p.allowed_values.map(v => `<option value="${v}">${v}</option>`).join('');
                inputHtml = `<select id="input-${p.id}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;">
                    <option value="">Select...</option>
                    ${options}
                </select>`;
            } else if (p.attribute_type === 'bool') {
                inputHtml = `<select id="input-${p.id}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;">
                    <option value="">Select...</option>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                </select>`;
            } else if (p.attribute_type === 'int' || p.attribute_type === 'float') {
                const step = p.attribute_type === 'float' ? '0.1' : '1';
                inputHtml = `<input type="number" id="input-${p.id}" step="${step}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;" placeholder="Enter number">`;
            } else {
                // String or other
                inputHtml = `<input type="text" id="input-${p.id}" style="width: 100%; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px;" placeholder="Type your answer">`;
            }
            
            html += `
                <tr style="border-bottom: 1px solid #dee2e6;" id="row-${p.id}">
                    <td style="padding: 12px; color: #666;">#${p.priority}</td>
                    <td style="padding: 12px;">${reasonBadge}</td>
                    <td style="padding: 12px; font-weight: 500; color: #333;">${p.task_title || 'User-level'}</td>
                    <td style="padding: 12px; color: #0066cc; font-weight: 500;">${p.attribute_label}</td>
                    <td style="padding: 12px;">${inputHtml}</td>
                    <td style="padding: 12px; color: #666;">${p.target_user_name}</td>
                    <td style="padding: 12px;">
                        <button onclick="savePendingAnswer('${p.id}', '${p.task_id}', '${p.target_user_id}', '${p.attribute_name}')" 
                                class="primary-btn" style="padding: 6px 12px; font-size: 0.85rem;">
                            💾 Save
                        </button>
                    </td>
                </tr>
            `;
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
        
        html += `
            <div style="margin-top: 24px; padding: 16px; background: #e7f3ff; border-radius: 8px; border-left: 4px solid #0066cc;">
                <h4 style="margin: 0 0 8px 0; color: #004085;">💡 Tip</h4>
                <p style="margin: 0; color: #004085; line-height: 1.6;">
                    Fill in your answers above and click <strong>💾 Save</strong> for each one. 
                    Or, go to <strong>🤖 Chat with Robin</strong> and type <code style="background: white; padding: 2px 6px; border-radius: 3px;">collect_data</code> 
                    to have Robin guide you through answering these questions conversationally.
                </p>
            </div>
        `;
        
        container.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading pending questions:', error);
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #dc3545;">
                <div style="font-size: 48px; margin-bottom: 16px;">❌</div>
                <p>Failed to load pending questions. Please try again.</p>
                <button onclick="loadPendingQuestions()" class="primary-btn" style="margin-top: 16px;">Retry</button>
            </div>
        `;
    }
}

async function savePendingAnswer(pendingId, taskId, targetUserId, attributeName) {
    const input = document.getElementById(`input-${pendingId}`);
    const value = input.value.trim();
    
    if (!value) {
        alert('Please enter a value before saving');
        return;
    }
    
    try {
        // Call the answers API
        const response = await apiCall('/answers', {
            method: 'POST',
            body: JSON.stringify({
                task_id: taskId === 'null' ? null : taskId,
                target_user_id: targetUserId,
                attribute_name: attributeName,
                value: value,
                refused: false
            })
        });
        
        // Success! Remove the row and show success message
        const row = document.getElementById(`row-${pendingId}`);
        row.style.backgroundColor = '#d4edda';
        row.innerHTML = `
            <td colspan="7" style="padding: 12px; text-align: center; color: #155724; font-weight: 500;">
                ✅ Answer saved successfully! Refreshing list...
            </td>
        `;
        
        // Reload after a short delay
        setTimeout(() => {
            loadPendingQuestions();
        }, 1500);
        
    } catch (error) {
        console.error('Error saving answer:', error);
        alert('Failed to save answer: ' + error.message);
    }
}


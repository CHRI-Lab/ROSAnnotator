// EditBooklistForm.tsx
import React, { useState } from 'react';
import { Button, TextareaAutosize } from '@mui/material';
import jsonData from '../../../public/predefined_booklist.json';  // 确保路径正确

const EditBooklistForm = ({ onSave }) => {
    const [jsonDataText, setJsonDataText] = useState(JSON.stringify(jsonData, null, 2));

    const handleSave = () => {
        try {
            const data = JSON.parse(jsonDataText);
            onSave(data);
        } catch (error) {
            alert('Invalid JSON data.');
        }
    };

    return (
        <div>
            <TextareaAutosize
                minRows={10}
                style={{ width: '100%' }}
                value={jsonDataText}
                onChange={(e) => setJsonDataText(e.target.value)}
            />
            <Button onClick={handleSave} variant="contained" color="primary">
                Save
            </Button>
        </div>
    );
};

export default EditBooklistForm;

// EditBooklistForm.tsx
import React, { useState } from "react";
import { Button, TextareaAutosize } from "@mui/material";

interface EditBooklistFormProps {
  bookListData: Record<string, string[]>;
  onSave: (data: any) => void;
}

const EditBooklistForm: React.FC<EditBooklistFormProps> = ({
  bookListData,
  onSave,
}) => {
  const [bookListDataText, setBookListDataText] = useState(
    JSON.stringify(bookListData, null, 2)
  );

  const handleSave = () => {
    try {
      const data = JSON.parse(bookListDataText);
      onSave(data);
    } catch (error) {
      alert("Invalid JSON data.");
    }
  };

  return (
    <div>
      <Button
        onClick={handleSave}
        variant="contained"
        color="primary"
        sx={{ marginTop: 2, marginBottom: 2 }}
      >
        Save
      </Button>
      <TextareaAutosize
        minRows={10}
        style={{ width: "100%" }}
        value={bookListDataText}
        onChange={(e) => setBookListDataText(e.target.value)}
      />
    </div>
  );
};

export default EditBooklistForm;

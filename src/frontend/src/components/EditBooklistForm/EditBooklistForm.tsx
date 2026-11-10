// EditBooklistForm.tsx
import React, { useState } from "react";
import { Button, TextareaAutosize } from "@mui/material";
import type { BookList } from "../../types/annotations";

interface EditBooklistFormProps {
  bookListData: BookList;
  onSave: (data: BookList) => void;
}

const isBookList = (value: unknown): value is BookList =>
  typeof value === "object" &&
  value !== null &&
  Object.values(value).every(
    (words) =>
      Array.isArray(words) && words.every((word) => typeof word === "string")
  );

const EditBooklistForm: React.FC<EditBooklistFormProps> = ({
  bookListData,
  onSave,
}) => {
  const [bookListDataText, setBookListDataText] = useState(
    JSON.stringify(bookListData, null, 2)
  );

  const handleSave = () => {
    try {
      const data: unknown = JSON.parse(bookListDataText);
      if (!isBookList(data)) {
        throw new Error("Booklist values must be arrays of strings.");
      }
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

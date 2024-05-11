import React, { useState, useEffect } from 'react';
import { TextField, styled, IconButton } from '@mui/material';


interface BlockProps {
  block: {
    start: number;
    end: number;
    text?: string;
  };
  duration: number;
  axisType: string;
  onSave: (text: string) => void;
  onDelete: () => void;  // 添加这个删除处理函数的prop
}

const BlockDisplay = styled('div')<{ start: number; end: number; duration: number }>(
  ({ theme, start, end, duration }) => ({
    position: 'absolute',
    left: `${(start / duration) * 100}%`,
    width: `${((end - start) / duration) * 100}%`,
    height: '80%',
    backgroundColor: theme.palette.action.selected,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',  // 调整对齐方式以容纳关闭按钮
    cursor: 'pointer',
    border: '1px solid black',
    boxSizing: 'border-box',
    padding: '0 10px',  // 添加内边距为关闭按钮留出空间
  })
);

const Block: React.FC<BlockProps> = ({ block, duration, axisType, onSave, onDelete }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [text, setText] = useState(block.text || '');

  useEffect(() => {
    setText(block.text || '');
  }, [block.text]);

  const handleDoubleClick = () => {
    if (axisType === 'type-in') {
      setIsEditing(true);
    }
  };

  const handleBlur = () => {
    onSave(text);
    setIsEditing(false);
  };

  return (
    <BlockDisplay
      start={block.start}
      end={block.end}
      duration={duration}
      onDoubleClick={handleDoubleClick}
    >
      {isEditing ? (
        <TextField
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={handleBlur}
          autoFocus
          fullWidth
        />
      ) : (
        <span>{text || 'Double-click to edit'}</span>
      )}
      <IconButton onClick={onDelete} size="small">
        x
      </IconButton>
    </BlockDisplay>
  );
};

export default Block;

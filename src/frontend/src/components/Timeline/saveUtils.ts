// saveUtils.ts

//strips file ext from filename string (recording.bag -> recording)
const stripExtension = (filename: string) => filename.replace(/\.[^/.]+$/, ""); 

// Builds the default annotation name shown when the save dialog opens
export const buildDefaultAnnotationName = (
    rosBagFileName: string,
    bookListFileName?: string
    ): string => {
    return `${stripExtension(rosBagFileName)}+${
        bookListFileName ? stripExtension(bookListFileName) : "noBookList"
    }`;
};

// Checks if the given annotation name is sensible. 
// Checks if name is empty, or contains any invalid characters
// returns reason for invalid name for error handling
export const isValidAnnotationName = (name: string): { valid: boolean; reason?: string } => {
    const trimmed = name.trim();

    if (!trimmed) {
        return { valid: false, reason: "Name cannot be empty." };
    }

    if (/[\\/:*?"<>|]/.test(trimmed)) {
        return { valid: false, reason: 'Name cannot contain any of: \\ / : * ? " < > |' };
    }

    if (/^\.+$/.test(trimmed)) {
        return { valid: false, reason: "Name cannot consist of only dots." };
    }

    return { valid: true };
};

//Collects the current annotation state into the JSON shape the backend expects
export const collectAnnotationData = (axes: any[]) => { 
    const data = axes.map((axis) => ({
        id: axis.id,
        axisType: axis.type,
        axisName: axis.axisName ? axis.axisName : "",
        axisBooklistName: axis.typeName ? axis.typeName : "",
        annotationBlocks: axis.blocks
        ? axis.blocks.map((block) => ({
            start: block.start,
            end: block.end,
            text: block.text,
            }))
        : [],
    }));
    console.log(data);
    return data;
};

export const postAnnotation = async (
    annotationName: string,
    annotationData: any
    ): Promise<void> => {
    const response = await fetch("http://localhost:8000/api/save_annotation/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
        annotation_name: annotationName,
        annotation_data: annotationData,
        }),
    });

    if (response.ok) {
        return;
    }

    // The serializer returns { field: ["reason", ...] }, which is far more
    // useful to the user than a generic message.
    if (response.status === 400) {
        const errors = await response.json().catch(() => null);
        const detail = errors
            ? Object.values(errors).flat().join(" ")
            : "The annotation could not be saved.";
        throw new Error(detail);
    }

    switch (response.status) {
    case 500:
        throw new Error("Internal server error");
    case 405:
        throw new Error("Method not allowed");
    default:
        throw new Error(`Unexpected error: ${response.status}`);
    }
};
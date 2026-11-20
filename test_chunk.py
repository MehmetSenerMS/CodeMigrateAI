from codemigrate.chunking.models import SourceChunk

#%% 
chunk = SourceChunk(
    chunk_id="chunk_001",
    source_type="code",
    file_path="legacy/CustomerService.cs",
    content="public string GetCustomerName(int id)",
    start_line=5,
    end_line=5,
    class_name="CustomerService",
    method_name="GetCustomerName"
)

print(chunk)

#%%
print("\n--- Validation Test ---")

try:
    invalid_chunk = SourceChunk(
        chunk_id="chunk_002",
        source_type="code",
        file_path="legacy/CustomerService.cs",
        content="public void Test()",
        start_line=20,
        end_line=10
    )

except ValueError as error:
    print("Validation caught:", error)


#%%
print("\n--- Multiple Validation Tests ---")

valid_data = {
    "chunk_id": "chunk_001",
    "source_type": "code",
    "file_path": "legacy/CustomerService.cs",
    "content": "public void Test()",
    "start_line": 1,
    "end_line": 10
}

test_cases = [
    ("chunk_id", ""),
    ("source_type", "invalid"),
    ("file_path", ""),
    ("content", ""),
    ("start_line", 0),
    ("end_line", 0)
]

for field, invalid_value in test_cases:

    test_data = valid_data.copy()
    test_data[field] = invalid_value

    try:
        SourceChunk(**test_data)
        print(f"FAIL: {field}")

    except ValueError as error:
        print(f"PASS: {field} -> {error}")
        
        
        
#%%

from codemigrate.chunking.code_chunker import CodeChunker


chunker = CodeChunker("legacy/CustomerService.cs")

source_code = chunker.read_source()

assert "class CustomerService" in source_code
assert "GetCustomerName" in source_code
assert "IsCustomerActive" in source_code

print("--- CodeChunker Test ---")
print("File:", chunker.file_path)
print("Characters:", len(source_code))
print("Read source: PASS")
print("\n--- Source Code ---")
print(source_code)

#%%

print("\n--- Brace Matching Test ---")

opening_index = source_code.index("{")
closing_index = chunker.find_matching_brace(
    source_code,
    opening_index
)

print("Opening index:", opening_index)
print("Closing index:", closing_index)
print("Closing character:", source_code[closing_index])

assert source_code[closing_index] == "}"
print("Brace matching: PASS")

#%%

print("\n--- Advanced Brace Matching Tests ---")

# TEST 1: Nested braces
nested_code = """public void Test()
{
    if (true)
    {
        Console.WriteLine("Hello");
    }
}"""

opening = nested_code.index("{")

closing = chunker.find_matching_brace(
    nested_code,
    opening
)

assert closing == nested_code.rfind("}")
print("TEST 1 - Nested braces: PASS")


# TEST 2: Invalid opening index
try:
    chunker.find_matching_brace(nested_code, 0)

except ValueError:
    print("TEST 2 - Invalid opening index: PASS")

else:
    raise AssertionError("Invalid index was accepted")


# TEST 3: Missing closing brace
invalid_code = "public void Test() {"

try:
    chunker.find_matching_brace(
        invalid_code,
        invalid_code.index("{")
    )

except ValueError:
    print("TEST 3 - Missing closing brace: PASS")

else:
    raise AssertionError("Missing closing brace was not detected")



#%%

print("\n--- Method Extraction Test ---")

chunks = chunker.extract_methods()

print("Total methods:", len(chunks))

for chunk in chunks:

    print("\n-------------------------")
    print("Chunk ID:", chunk.chunk_id)
    print("Class:", chunk.class_name)
    print("Method:", chunk.method_name)
    print("Start line:", chunk.start_line)
    print("End line:", chunk.end_line)
    print("Content:")
    print(chunk.content)

assert len(chunks) == 2

assert {c.method_name for c in chunks} == {
    "GetCustomerName",
    "IsCustomerActive"
}

assert all(c.start_line <= c.end_line for c in chunks)

print("\nMethod extraction: PASS")

#%%

print("\n--- String and Comment Brace Test ---")

tricky_code = '''public void Example()
{
    string text = "}";
    // }
    /* } */
    char marker = '}';
    string verbatim = @"some "" } text";

    if (true)
    {
        Console.WriteLine("{");
    }
}'''

opening = tricky_code.index("{")

closing = chunker.find_matching_brace(
    tricky_code,
    opening
)

expected_closing = tricky_code.rfind("}")

print("Expected closing index:", expected_closing)
print("Actual closing index:", closing)

assert closing == expected_closing

print("String and comment handling: PASS")

#%%

print("\n--- Multiple Class Detection Test ---")

multi_chunker = CodeChunker(
    "legacy/MultipleServices.cs"
)

multi_chunks = multi_chunker.extract_methods()

actual = {}

for chunk in multi_chunks:
    actual[chunk.method_name] = chunk.class_name

    print(
        f"Method: {chunk.method_name} "
        f"-> Class: {chunk.class_name}"
    )

expected = {
    "GetNumber": "FirstService",
    "IsActive": "SecondService"
}

assert actual == expected, (
    f"Expected {expected}, but got {actual}"
)

print("Multiple class detection: PASS")


#%%

print("\n--- Inheritance Detection Test ---")

inheritance_chunker = CodeChunker(
    "legacy/PremiumCustomerService.cs"
)

inheritance_chunks = inheritance_chunker.extract_methods()

assert len(inheritance_chunks) == 1

chunk = inheritance_chunks[0]

print("Method:", chunk.method_name)
print("Detected class:", chunk.class_name)

assert chunk.method_name == "HasPremiumAccess"

assert chunk.class_name == "PremiumCustomerService", (
    f"Incorrect class detected: {chunk.class_name}"
)

print("Inheritance detection: PASS")

#%%

print("\n--- Generic Class Detection Test ---")

generic_chunker = CodeChunker(
    "legacy/GenericRepository.cs"
)

generic_chunks = generic_chunker.extract_methods()

assert len(generic_chunks) == 1

chunk = generic_chunks[0]

print("Method:", chunk.method_name)
print("Detected class:", chunk.class_name)
print("Content:", chunk.content)

assert chunk.method_name == "GetById"

assert chunk.class_name == "Repository", (
    f"Incorrect class detected: {chunk.class_name}"
)

print("Generic class detection: PASS")


#%% 

print("\n--- Generic Class Detection Test ---")

generic_chunker = CodeChunker(
    "legacy/GenericRepository.cs"
)

generic_chunks = generic_chunker.extract_methods()

assert len(generic_chunks) == 1

chunk = generic_chunks[0]

print("Method:", chunk.method_name)
print("Detected class:", chunk.class_name)
print("Content:", chunk.content)

assert chunk.method_name == "GetById"

assert chunk.class_name == "Repository", (
    f"Incorrect class detected: {chunk.class_name}"
)

print("Generic class detection: PASS")

#%%

print("\n--- Generic Method Detection Test ---")

generic_method_chunker = CodeChunker(
    "legacy/GenericMethodService.cs"
)

generic_method_chunks = generic_method_chunker.extract_methods()

detected_methods = {
    chunk.method_name
    for chunk in generic_method_chunks
}

print("Detected methods:", detected_methods)

expected_methods = {
    "ConvertValue",
    "GetName"
}

assert detected_methods == expected_methods, (
    f"Expected {expected_methods}, "
    f"but got {detected_methods}"
)

assert len(generic_method_chunks) == 2

print("Generic method detection: PASS")





# Multiple languages (variants)

A single coding question can be solved in more than one language. Each language
is stored as a _variant_ with its own sample/hidden test I/O (expected output
differs per language) plus optional starter code.

- API field: `code_variants: [{ language, starter_code?, code_sample_input?,
code_sample_output?, code_hidden_input?, code_hidden_output? }]`. `language`
  must be one of `python`, `typescript`, `java`.
- The player-facing question response also includes `available_languages`, and
  the answer-submit request accepts an optional `language` selecting which
  variant to grade against (defaults to the question's primary language).
- The legacy flat `code_*` fields documented below still work as a
  single-language fallback; they mirror the primary (first) variant for
  backward compatibility, and existing questions are backfilled into one
  variant automatically.

The per-language evaluation contracts are described next.

# Python

A player will be asked to provide code to solve a problem. The player will be presented with:

- Problem Description (e.g. "Write Python code that takes a number `n` and sets `result` to the sum of 1 to n.")
- Correct Answer this is not used coding questions as the evaluation engine will use the code submitted together with the inputs to see if the outputs match (and hence the correct answer)
- Sample input that is displayed when the player uses Hint (e.g.'{"n": 5}')
- Sample output that is used with the code submitted to validate the sample input (e.g. "15")
- Hidden input and hidden output that are never displayed to the player, but will be used to validate the code to ensure that the code submitted is not hard coded.
- Hint provides the player with something that will help them towards to problem (and display the sample input/outputs) - (e.g.Think about the range() function")

The evaluation logic that the game engine uses is as follows:

```
inputs = { dependant on question inputs}           # <-- code_sample_input
for k, v in inputs.items():
    globals()[k] = v

# <-- player's code goes here -->

print(result)                # must match code_sample_output
```

Some examples of how this works.

example one (easy)

{
"category": "Coding",
"difficulty": "Easy",
"description": "Given 3 variables, write code so that result = the sum of the 3 numbers. Input:- a: First number - b: Second number- c: Third number",
"correct_answer": "",
"code_programming_language": "python",
"code_sample_input": "{'a': 13, 'b': 17, 'c': 10}",
"code_sample_output": "40",
"code_hidden_input": "{'a': 20, 'b': 30, 'c': 15}",
"code_hidden_output": "65",
"hint": "Do not overthink - a one liner with the right arithmic operation should do it"
}

example two (moderate)

{
"category": "Coding",
"difficulty": "Moderate",
"description": "Parse an AWS CloudFront URL to extract its components.The function should extract and return these components in a dictionary: 1. distribution_id: The CloudFront distribution ID (the part after 'https://' and before '.cloudfront.net') 2. resource_path: The path to the resource (everything after '.cloudfront.net') 3. resource_type: The file extension (e.g., 'png', 'jpg', 'html') without the dot Input:- url: A CloudFront URL",
"correct_answer": "",
"code_programming_language": "python",
"code_sample_input": "{'url': 'https://d2cxyz987.cloudfront.net/index.html'}",
"code_sample_output": "{'distribution_id': 'd2cxyz987', 'resource_path': '/index.html', 'resource_type': 'html'}",
"code_hidden_input": "{'url': 'https://d111111abcdef8.cloudfront.net/images/product/main.jpg'}",
"code_hidden_output": "{'distribution_id': 'd111111abcdef8', 'resource_path': '/images/product/main.jpg', 'resource_type': 'jpg'}",
"hint": "Looks like some string/url manipulation is called for"
}

example three (moderate)

{
"category": "Coding",
"difficulty": "Easy",
"description": "Given the array of tuples. Write code so that result is equal to the array ordered by the second value of each tuple Input:- a1: An array of tuples",
"correct_answer": "",
"code_programming_language": "python",
"code_sample_input": "{'a1': [(5, 10), (2, 5), (9, 7)]}",
"code_sample_output": "[(2, 5), (9, 7), (5, 10)]",
"code_hidden_input": "{'a1': [(1, 2), (3, 3), (1, 1)]}",
"code_hidden_output": "[(1, 1), (1, 2), (3, 3)]",
"hint": "Looks like some array manipulation in Python is needed"
}

# TypeScript

A player will be asked to provide code to solve a problem. The player will be presented with:

- Problem Description (e.g. "Given a number `n`, set `result` to the sum of all integers from 1 to n.")
- Correct Answer this is not used coding questions as the evaluation engine will use the code submitted together with the inputs to see if the outputs match (and hence the correct answer)
- Sample input that is displayed when the player uses Hint (e.g.'{"n": 5}')
- Sample output that is used with the code submitted to validate the sample input (e.g. "15")
- Hidden input and hidden output that are never displayed to the player, but will be used to validate the code to ensure that the code submitted is not hard coded.
- Hint provides the player with something that will help them towards to problem (and display the sample input/outputs) - (e.g.Use a for loop or the formula n\*(n+1)/2)

The evaluation logic that the game engine uses is as follows:

```
const inputs = { dependant on question inputs };        // <-- code_sample_input, injected literally
Object.assign(globalThis, inputs);

// <-- player's code goes here -->

console.log(result);
```

So with the above example, the evaluation logic looks like this

```
const inputs = {"n": 5};
Object.assign(globalThis, inputs);

let result = 0; for (let i = 1; i <= n; i++) result += i;

console.log(result);
// stdout: "15" — matches code_sample_output ✓
```

Examples of questions (easy)

```
{
  "category": "Coding",
  "difficulty": "Easy",
  "description": "Given a number `n`, set `result` to the sum of all integers from 1 to n.",
  "correct_answer": " ",
  "code_programming_language": "typescript",
  "code_sample_input": "{\"n\": 5}",
  "code_sample_output": "15",
  "code_hidden_input": "{\"n\": 100}",
  "code_hidden_output": "5050",
  "hint": "Use a for loop or the formula n*(n+1)/2"
}
```

Example (moderate)

```
{
  "category": "Coding",
  "difficulty": "Moderate",
  "description": "Given a nested array `arr` of numbers (which can contain arrays within arrays), set `result` to a flat array of all the numbers in order. For example, [1, [2, [3, 4]], 5] should become [1, 2, 3, 4, 5].",
  "correct_answer": " ",
  "code_programming_language": "typescript",
  "code_sample_input": "{"arr": [1, [2, [3, 4]], 5]}",
  "code_sample_output": "1,2,3,4,5",
  "code_hidden_input": "{"arr": [[2, 1], [3, [4, [5, [6]]]], 7, [8, 9]]}",
  "code_hidden_output": "1,2,3,4,5,6,7,8,9",
  "hint": "Look into Array.prototype.flat() with a depth argument, or write a recursive solution."
}
```

Example (hard)

```
{
  "category": "Coding",
  "difficulty": "Hard",
  "description": "Given a string `s`, set `result` to the length of the longest substring that contains no repeating characters. For example, for 'abcabcbb' the answer is 3 ('abc').",
  "correct_answer": " ",
  "code_programming_language": "typescript",
  "code_sample_input": "{"s": "abcabcbb"}",
  "code_sample_output": "3",
  "code_hidden_input": "{"s": "pwiekewpwie"}",
  "code_hidden_output": "4",
  "hint": "Consider a sliding window approach with two pointers and a Set or Map to track characters you've seen."
}
```

# Java

A player will be asked to provide code to solve a problem. The player will be presented with:

- Problem Description (e.g. "Write a Java solve() method that takes a JSON string input containing two numbers x and y, parses them, and returns their sum as a String.")
- Correct Answer this is not used coding questions as the evaluation engine will use the code submitted together with the inputs to see if the outputs match (and hence the correct answer)
- Sample input that is displayed when the player uses Hint (e.g.'{"x": 2, "y": 3}')
- Sample output that is used with the code submitted to validate the sample input (e.g. "5")
- Hidden input and hidden output that are never displayed to the player, but will be used to validate the code to ensure that the code submitted is not hard coded.
- Hint provides the player with something that will help them towards to problem (and display the sample input/outputs) - (e.g.Think about the range() function")

The evaluation logic that the game engine uses is as follows:

```
import java.util.*;

public class Solution {
    // <-- your submitted code gets pasted here -->

    public static void main(String[] args) {
        String input = "{"x": 2, "y": 3}";  // <-- test_input as a Java string literal
        System.out.println(solve(input));         // <-- calls your solve() method
    }
}
```

Example question (easy)

```
{
    "category": "Coding",
    "difficulty": "Easy",
    "code_hidden_input": "{"x": 10, "y": 20}",
    "code_hidden_output": "30",
    "code_programming_language": "java",
    "code_sample_input": "{"x": 2, "y": 3}",
    "code_sample_output": "5",
    "correct_answer": "",
    "description": "Write a Java solve() method that takes a JSON string input containing two numbers x and y, parses them, and returns their sum as a String.",
    "hint": "Parse the JSON string to extract x and y, then return their sum"
}
```

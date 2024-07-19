from tools import data_sample, context_process, query_model, explore_atomic_facts, read_chunk, read_neighbor_node, \
    answer_reason
from template import rational_plan, initial_node_selection, LLM_Rating_1


def GraphReader(example, split_size):
    print("*************************START Reader*******************************")
    # 生成关键词关联图
    context_map, node_set, G = context_process(example, split_size)
    print("***********CREATE Graph************")
    # 生成任务计划
    query = rational_plan.format(example['question'])
    plan_text = query_model(prompt=query)
    print(f"**********Rational plan************\n{plan_text}")
    history = {
        "Question": example['question'],
        "Rational plan": plan_text,
        "Previous actions": ["Pre-plan And Select Initial Nodes"],
        "Notebook": "None"
    }
    # 初始化结点
    query = initial_node_selection.format(example['question'], plan_text, node_set.keys())
    initial_res = query_model(prompt=query)
    initial_node_ls = []
    for item in initial_res.strip().split('\n'):
        ini_node = str(item).split(',')[0].split(':')[-1].strip()
        if ini_node in node_set.keys():
            initial_node_ls.append(ini_node)
    initial_node_ls = iter(initial_node_ls)
    initial_node = next(initial_node_ls)
    current_node = initial_node
    print(f"**********Initial Node*************\n{initial_node}")
    history["Previous actions"].append(f"Initial Node: {initial_node}")
    Chosen_Action, history, answer = explore_atomic_facts(initial_node, node_set, history)
    print(f"**********Chosen Action************")
    while True:
        if "search_more" in Chosen_Action:
            print(Chosen_Action)
            Chosen_Action, history, answer = read_neighbor_node(current_node, G, history)
        elif "explore_atomic_facts" in Chosen_Action:
            print(Chosen_Action)
            if answer in node_set.keys():
                current_node = answer
                Chosen_Action, history, answer = explore_atomic_facts(current_node, node_set, history)
            else:
                current_node = next(initial_node_ls)
                Chosen_Action, history, answer = explore_atomic_facts(current_node, node_set, history)
        elif "stop_and_read_neighbor" in Chosen_Action:
            print(Chosen_Action)
            Chosen_Action, history, answer = read_neighbor_node(current_node, G, history)
        elif "read_chunk" in Chosen_Action:
            print(Chosen_Action)
            Chosen_Action, history, answer = read_chunk(Chosen_Action, context_map, history)
        elif "termination" in Chosen_Action:
            print(Chosen_Action)
            answer = answer_reason(history)
            print(f"**********Final Answer*************")
            print(f"Question: {history['Question']}\nNotebook: {history['Notebook']}")
            print(f"The answer of AI is: {answer.replace('[answer]', '').replace('[answerable]', '')}")
            break
        else:
            print(f"**********Final Answer*************")
            print(f"Question: {history['Question']}\nNotebook: {history['Notebook']}")
            print(f"The answer of AI is: {answer.replace('[answer]', '').replace('[answerable]', '')}")
            break
    print(f"The ground truth answer: {example['answer']}")
    query = LLM_Rating_1.format(example['question'], answer, example['answer'])
    result = query_model(prompt=query)
    print(f"Is the answer correct: {result}")


if __name__ == '__main__':
    # 抽取测试样本
    data_iterator = data_sample()
    # sample = next(data_iterator)
    # 设置窗口大小
    chunk_size = 2000
    for i in data_iterator:
        GraphReader(i, chunk_size)



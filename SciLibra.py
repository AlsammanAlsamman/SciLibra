#!/usr/bin/python
'''
* FILENAME :        SciLibra            
*
* DESCRIPTION : Scientific Library for academic and research users
* The purpose of this library is to provide an android application for managing scientific papers and references on mobile devices
* Additionally it can be used for operating systems such as Linux, Windows, and Mac OS
*
* AUTHOR :    Alsamman M Alsamman        START DATE :    16 Aug 2023
* EMAIL : smahmoud@ageri.sci.eg ,  A.Alsamman@cgiar.org
* 
'''

import os
import sys
import time
import datetime
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
import sqlite3
from kivy.uix.boxlayout import BoxLayout
# tree view
from kivy.uix.treeview import TreeView, TreeViewLabel, TreeViewNode
# import widget for scroll view
from kivy.uix.widget import Widget
# from scroll view
from kivy.uix.scrollview import ScrollView
# import properties for the app
from kivy.properties import ObjectProperty
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
# import bibtexparser
# file dialog
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.factory import Factory
from kivy.uix.floatlayout import FloatLayout
import sqlite3
import bibtexparser
import webbrowser



################# Parameters #####################
article_groupSelected = "biology"
articles_treeview_clustering = "Author"
articles_treeview_clusters = ["Year", "Journal", "Author", "Keyword", "TagGroup"]
Article_sub_tables = ["TagGroup", "Author", "Keyword", "Year", "Journal", "FolderPath", "Comment"]
Article_sub_tables_info = {"TagGroup":"groups", "Author":"author", "Keyword":"keyword", "Year":"year", "Journal":"journal", "FolderPath":"pdffolderpath", "Comment":"comment"}
# Dictionary for the article info table
Article_infoTable ={"author":"Author", "year":"Year", "journal":"Journal", 
                    "groups":"TagGroup", "url":"url", "pdffolderpath":"FolderPath", "filepath":"FilePath", "comment":"Comment"}
############################### Functions ###############################

bibFile = "/home/samman/Documents/MobileApplications/Learn/LibraryKivy/Article.bib"

################ Handle bibtex file ################

# read bibtex file and return a list of articles
def read_bibfile(bibtexFile):
    bib_database = None
    with open(bibtexFile) as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file)
    return bib_database.entries

# write a bibtex entry to string
def write_bibentry_to_string(articlekey, title, authors, year, journal, articlegroups,  url, pdffolderpath, filepath):
    # write a bibtex entry to string
    bibtex_entry = "@article{" + articlekey + ",\n"
    bibtex_entry += "title={" + title + "},\n"
    bibtex_entry += "author={" + authors + "},\n"
    bibtex_entry += "year={" + year + "},\n"
    bibtex_entry += "journal={" + journal + "},\n"
    bibtex_entry += "groups={" + articlegroups + "},\n"
    if not url is None:
        bibtex_entry += "url={" + url + "},\n"
    if not pdffolderpath is None:
        bibtex_entry += "pdffolderpath={" + pdffolderpath + "},\n"
    if not filepath is None:
        bibtex_entry += "filepath={" + filepath + "},\n"
    bibtex_entry += "\}\n"
    return bibtex_entry

################ Handle database ################
def create_database():
        # create a database
        conn = sqlite3.connect('articles.db')
        c = conn.cursor()
        # create the main table for articles
        c.execute('''CREATE TABLE articles
                     (ArticleKey text, Title text, Authors text, Year integer, Journal text, TagGroups text, url text, folderpath text, comment text)''')
        # create the sub tables for articles
        for table in Article_sub_tables:
            c.execute('''CREATE TABLE {} (ArticleKey text, {} text)'''.format(table, Article_sub_tables_info[table]))
            print("Created table {}".format(table))
        # save changes
        conn.commit()
        # close connection
        conn.close()

## Add functions
# insert article into the database
def insert_article(ArticleInfo):
    # get article info
    ArticleKey = ArticleInfo["ID"]
    Title = ArticleInfo["title"]
    Authors = ArticleInfo["author"]
    Year = ArticleInfo["year"]
    Journal = ArticleInfo["journal"]
    TagGroup = ArticleInfo["groups"]
    
    comment = ""
    FolderPath = ""
    url = ""
    if "comment" in ArticleInfo:
        comment = ArticleInfo["comment"]
    if "url" in ArticleInfo:
        url = ArticleInfo["url"]
    if "folderpath" in ArticleInfo:
        FolderPath = ArticleInfo["folderpath"]

    ## connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    
    ## is the article already in the database
    c.execute('''SELECT * FROM articles WHERE ArticleKey=?''', (ArticleKey,))
    data = c.fetchone()
    # if the article is in the database return False !! add a message to the user
    if not data is None:
        return False
    
    # insert article into the database (Major table)
    c.execute('''INSERT INTO articles (ArticleKey, Title, Authors, Year, Journal, TagGroups, url, folderpath, comment) VALUES (?,?,?,?,?,?,?,?,?)''', (ArticleKey, Title, Authors, Year, Journal, TagGroup, url, FolderPath, comment))
    # add article information to sub tables
    for info in ArticleInfo:
        if info in ArticleInfo and info in Article_infoTable:
            for item in ArticleInfo[info].split(","):
                c.execute('''INSERT INTO {} (ArticleKey, {}) VALUES (?,?)'''.format(Article_infoTable[info], info), (ArticleKey, item))
                
    # save changes
    conn.commit()
    # close connection
    conn.close()
    # return True if the article is inserted
    return True



######### Get functions ##########

# get all articles titles from the database
def get_info_from_main_table(info_type):
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles titles
    c.execute('''SELECT {} FROM articles'''.format(info_type))
    data = c.fetchall()
    # close connection
    conn.close()
    # convert data to a list
    data = [item[0] for item in data]
    # return data
    return data


# get all articles keys from the sub table for a specific info value
def get_info_from_sub_table(info_type, info):
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles titles
    c.execute('''SELECT ArticleKey FROM {} WHERE {}=?'''.format(info_type, Article_sub_tables_info[info_type]), (info,))
    data = c.fetchall()
    # close connection
    conn.close()
    # convert data to a list
    data = [item[0] for item in data]
    # return data
    return data

# get all articles titles from the database  for a set of articles keys
def get_titles_from_database_for_keys(keys):
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles titles
    c.execute('''SELECT Title FROM articles WHERE ArticleKey IN ({})'''.format(','.join('?' for _ in keys)), keys)
    data = c.fetchall()
    # close connection
    conn.close()
    # convert data to a list
    data = [item[0] for item in data]
    # return data
    return data

# get all articlekeys from sub table
def get_articleKeys_from_sub_table(sub_table):
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles titles
    c.execute('''SELECT ArticleKey FROM {}'''.format(sub_table))
    data = c.fetchall()
    # close connection
    conn.close()
    # convert data to a list
    data = [item[0] for item in data]
    # remove duplicates
    data = list(set(data))
    return data

# get information for a cluster from the database table and return a dictionary
def get_ArticleKeys_from_Table_as_Clusters(table):
    print("####################")
    print(table)
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles ArticleKey as clusters
    c.execute('''SELECT ArticleKey, {} FROM {}'''.format(Article_sub_tables_info[table], table))
    data = c.fetchall()
    # close connection
    conn.close()
    # convert data to a dictionary with values of lists
    clusters = {item[1]:[] for item in data}
    # add articles to the dictionary
    for item in data:
        clusters[item[1]].append(item[0])
    return clusters

# get article info from the database
def get_article_info_from_database(articlekey):
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles titles
    c.execute('''SELECT * FROM articles WHERE ArticleKey=?''', (articlekey,))
    data = c.fetchone()
    # close connection
    conn.close()
    
    # convert data to a dictionary
    data = {"ArticleKey":data[0], "Title":data[1], "Authors":data[2], "Year":data[3], "Journal":data[4]}
    # return data
    return data

# get article TagGroups from the database
def get_TagGroups():
    # connect to the database
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    # get all articles titles
    c.execute('''SELECT groups FROM TagGroup''')
    data = c.fetchall()
    # close connection
    conn.close()
    # convert data to a list
    data = [item[0] for item in data]
    # remove duplicates
    data = list(set(data))
    # return data
    return data


# if the database does not exist then create it
if not os.path.isfile("articles.db"):
    create_database()

# read the bibtex file
Articles = read_bibfile(bibFile)

# insert articles into the database
success = 0
for article in Articles:
    if insert_article(article):
        success += 1
print("Inserted {} articles".format(success))



################# Global Variables #####################
# TreeArticles = {}


########## Classes ############
class MenuBar(BoxLayout):
    article_groups = ObjectProperty(None)
    # get the tree view from the main screen
    tree_view = property(lambda self: self.parent.ids.tree_view)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)     

    def show_help(self):
        pass
    
    def show_about(self):
        # show a new window with about information
        pass
    
    def add_article(self):
        pass
    
    def dismiss_popup(self):
        self._popup.dismiss()
    
    def load(self, path, filename):
        # with open(os.path.join(path, filename[0])) as stream:
        #     # self.read_bibfile(os.path.join(path, filename[0]))
        #     print(read_bibfile(bibFile))
        self.dismiss_popup()
        pass

    def show_load(self):
        content = LoadDialog(load=self.load, cancel=self.dismiss_popup)
        self._popup = Popup(title="Load file", content=content,
                            size_hint=(0.9, 0.9))
        self._popup.open()
    
    def select_article_cluster(self, cluster, cluster_buttons):
        for cbtn in cluster_buttons:
            if cbtn.text != cluster:
                cbtn.background_color = (1,1,1,1)
                cbtn.color = (1,0,0,1)
            else:
                cbtn.color = (1,1,1,1)
                cbtn.background_color = (1,0,0,1)

        # get the articles titles for the selected group
        ArticlesKeys = get_ArticleKeys_from_Table_as_Clusters(cluster)
        # get the articles titles for the selected group
        ArticlesTitlesDict = {}
        for key in ArticlesKeys:
            ArticlesTitlesDict[key] = get_titles_from_database_for_keys(ArticlesKeys[key])

        # clear nodes from the tree view
        for node in [i for i in  self.tree_view.iterate_all_nodes()]:
             self.tree_view.remove_node(node)
        # clear the global variable
        TreeArticles = {}
        # add new nodes to the tree view
        for key in ArticlesTitlesDict:
            # add a node for the cluster with the cluster name and number of articles in the cluster
            cluster_node = self.tree_view.add_node(TreeViewLabel(text=str(key) + " (" + str(len(ArticlesTitlesDict[key])) + ")"))
            # add articles to the cluster node
            for article in ArticlesTitlesDict[key]:
                # now you need to make the article key here rather than the title using the !!!!!!!!
                # self.tree_view.add_node(ArticleListLabel(text=article, refs={"ArticleKey":article}), cluster_node)
                ArLabel=ArticleListLabel(text=article, ArticleKey=article)
                self.tree_view.add_node(ArLabel, cluster_node)
                # add article to the global variable
        

class LoadDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)

# Create a better ArticleInfo class that inherits from widget
class ArticleInfo(TextInput):
    pass
 
class ArticleListLabel(TreeViewLabel):
    # add a new property to the class
    ArticleKey = ""
    def __init__(self, ArticleKey=None, **kwargs):
        super().__init__(**kwargs)
        self.ArticleKey = ArticleKey
        
    def on_touch_down(self, touch):
        # print object id
        # print(id(self))
        print(self.ArticleKey)
        ArticlePath="/home/samman/Documents/MobileApplications/Learn/LibraryKivy/Library/sequino2022omics.pdf"
        
        # # if system is linux then open the pdf file
        # if sys.platform == "linux":
        #     os.system("xdg-open " + ArticlePath)
        # else:
        #     webbrowser.open(ArticlePath)
        #self.parent.parent.parent.parent.ids.article_info.text=self.text

class ArticleGroups(DropDown):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # add some buttons
        
class MainScreen(GridLayout):
    tree_view = ObjectProperty(None)
    menu_bar = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        #get the articles titles from the database
        ArticlesTitles = get_info_from_main_table("Title")
        n = 1
        for article in ArticlesTitles:
            n += 1 # to get the information for each article
            self.tree_view.add_node(ArticleListLabel(text=article, ArticleKey=n))

        # add article clusters
        cluster_buttons = []
        for cluster in articles_treeview_clusters:
            btn = Button(text=cluster, size_hint_y=None, height=44, background_color = (1,1,1,1), color=(1,0,0,1))
            # if the group is selected then change the background color to red
            if cluster == articles_treeview_clustering:
                btn.background_color = (1,0,0,1)
                btn.color = (1,1,1,1)
            cluster_buttons.append(btn)
        
        # add buttons to the tree_view_drop
        for cbtni in range(len(cluster_buttons)):
            # white color code (1,1,1,1)
            # gbtn.bind(on_release=lambda btn: self.menu_bar.select_article_group(gbtn.text , gbtn))
            cluster_buttons[cbtni].bind(on_release=lambda btn: self.menu_bar.select_article_cluster(btn.text , cluster_buttons))
            self.menu_bar.tree_view_drop.add_widget(cluster_buttons[cbtni])

class SciLibra(App):
    def build(self):
        # create a database
        # create_database()
        return MainScreen()

if __name__ == '__main__':
    SciLibra().run()
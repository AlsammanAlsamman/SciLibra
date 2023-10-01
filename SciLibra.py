#!/usr/bin/python


############################################## About Author #########################################
# Created by: Alsamman M. Alsamman                                                                  #
# Emails: smahmoud [at] ageri.sci.eg or A.Alsamman [at] cgiar.org or SammanMohammed [at] gmail.com  #
# License: MIT License - https://opensource.org/licenses/MIT                                        #
# Disclaimer: The script comes with no warranty, use at your own risk                               #
# This script is not intended for commercial use                                                    #
#####################################################################################################


################# Imports #####################
import os
import sys
import webbrowser

################# Kivy Imports #####################
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.treeview import TreeView, TreeViewLabel, TreeViewNode
from kivy.uix.widget import Widget
from kivy.uix.scrollview import ScrollView
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.factory import Factory
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from pylatexenc.latex2text import LatexNodes2Text
from kivy.core.clipboard import Clipboard
from kivy.uix.actionbar import ActionButton

################# Local Imports #####################
import librarydatabase
import articledata

################# Global Variables #####################
# Main Table
articleInfoTable = {'ID': 'text',
                'title': 'text',
                'author': 'text',
                'year': 'integer',
                'journal': 'text',
                'taggroups': 'text',
                'url': 'text',
                'folderpath': 'text',
                'keywords': 'text',
                'abstract': 'text',
                'ENTRYTYPE': 'text',
                'pages': 'text',
                'volume': 'text',
                'number': 'text',
                'publisher': 'text',
                'bibtext': 'text'}
# Sub Tables
dbSubTablesInfo = {'taggroups': 'text'
            , 'author': 'text'
            , 'title': 'text'
            , 'keywords': 'text'
            , 'year': 'integer'
            , 'journal': 'text'
            , 'comment': 'text'
            , 'firstpageimages': 'blob'}

# Clustering Categories
clusteringCategories = ['title', 'author', 'year', 'journal', 'taggroups', 'keywords']



# Kivy TreeView Clusters
TreeCluster_Buttons = None
PreviousArticleClickedKey = None

SciLibraDatabaseName = "scilibraLibrary.db"

ExampleBibFile = "Articles_example.bib" #!!
DefultFolderPath = "/home/samman/Documents/MobileApplications/Learn/SciLibra" #!!
########## Classes ############
class MenuBar(BoxLayout):
    article_groups = ObjectProperty(None)
    # get the tree view from the main screen
    tree_view = property(lambda self: self.parent.parent.ids.tree_view)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)     

    def show_help(self):
        pass
    
    def show_about(self):
        # open the about popup
        about = Popup(title="About SciLibra", content=Label(text='''SciLibra is a free and open source software for managing scientific articles.
                                                            
Created by: Alsamman M. Alsamman
Emails: smahmoud [at] ageri.sci.eg 
        A.Alsamman [at] cgiar.org 
        SammanMohammed [at] gmail.com
                                                            
License: MIT License - https://opensource.org/licenses/MIT
Disclaimer: The script comes with no warranty, use at your own risk
This script is not intended for commercial use'''), size_hint=(0.7, 0.7))
        about.open()
        pass
    
    def add_article(self):
        pass
    
    def dismiss_popup(self):
        self._popup.dismiss()
    
    def load(self, path, filename):
        notinserted = []
        
        entries=articledata.read_bibfile(filename[0])
        # create connection
        libcon = librarydatabase.create_connection('scilibraLibrary.db')
        notinserted = librarydatabase.insertArticleSet2Library(libcon, entries, articleInfoTable, dbSubTablesInfo)
        # close connection
        libcon.close()
        self.dismiss_popup()
        if len(notinserted) > 0:
            # create a popup message
            notinsertedn=len(notinserted)
            popup = PopUpMessage(title="Not Inserted Articles", message="The following " + str(notinsertedn) + " articles are not inserted:\n" + "\n".join(notinserted))
            # open the popup
            popup.open()
        else:
            # create a popup message
            popup = PopUpMessage(title="Inserted Articles", message="All articles are inserted successfully")
            # open the popup
            popup.open()
        pass

    def show_load(self):
        # show the file chooser
        content = LoadDialog(load=self.load, cancel=self.dismiss_popup)
        self._popup = Popup(title="Load file", content=content,
                            size_hint=(0.9, 0.9), auto_dismiss=False)
        self._popup.open()
        pass
    def select_article_cluster(self, Category):
        global SciLibraDatabaseName
        # change the selection color
        CategoryiesDropDown.changeSelectionColor(Category)
        # get the articles IDs for this category
        # open the database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # create a new tree view with the new clustering category
        LibraryTreeview.createTreeView(self.tree_view, libcon, Category)
        # close connection
        libcon.close()
        
   
    def updatefolderpath(self):
        updateLoader = UpdateFolderPath()
        updateLoader.open()

class PopUpMessage(Popup):
    message = StringProperty('')
    def __init__(self, message=None, **kwargs):
        super().__init__(**kwargs)
        self.message = message
    def copy_message(self):
        # copy the message to clipboard
        Clipboard.copy(self.message)
        # close the popup
        self.dismiss()

class LoadDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)

class ArticleInfo(TextInput):
    pass

class LoadFolderDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)
    startPath = ObjectProperty(None)
    
class UpdateFolderPath(Popup):
    cancel = ObjectProperty(None)
    folder_paths=ObjectProperty(None)
    FolderPaths=[]
    
    def selectfolder(self):
        # show the file chooser
        content = LoadFolderDialog(load=self.load, cancel=self.dismiss_popup, startPath=DefultFolderPath)
        self._popup = Popup(title="Load file", content=content,
                            size_hint=(0.9, 0.9))
        self._popup.open()
        # self.cancel()
    
    def load(self, path, filename):
        global FolderPaths
        # create RstDocument format
        self.folder_paths.text += "+\t"+path+"\n"
        # add the path to the list
        self.FolderPaths.append(path)
        self.dismiss_popup()

    def dismiss_popup(self):
        self._popup.dismiss()

    def updatefolderpaths(self):
        # list all pdf files in the folder_paths
        pdfList = []
        for folder in self.FolderPaths:
            if folder != "":
                pdfList += [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".pdf")]
        # open the database
        global SciLibraDatabaseName
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article keys
        # The article keys are the file names without the extension and the path
        ArticleKeys = [os.path.splitext(os.path.basename(pdf))[0] for pdf in pdfList]
        #paths
        FolderPaths = [os.path.dirname(pdf) for pdf in pdfList]
        print(ArticleKeys)
        # update the folder path for all articles
        forceUpdate = True
        librarydatabase.updateMainTableRowSet(libcon, 'folderpath', ArticleKeys, FolderPaths, forceUpdate)
        # get properties
        libraryProperties = librarydatabase.getLibraryProperties(libcon)
        if libraryProperties["firstpageimage"] =="yes":
            for i in range(len(ArticleKeys)):
                librarydatabase.insertArticle2firstPageImage(libcon, FolderPaths[i], ArticleKeys[i], libraryProperties["firstpageimageresolution"])
        # close connection
        libcon.close()
class ArticleListLabel(TreeViewLabel):
    # add a new property to the class
    ArticleKey = ""
    def __init__(self, ArticleKey=None, **kwargs):
        super().__init__(**kwargs)
        self.ArticleKey = ArticleKey
        
    def on_touch_down(self, touch):
        ## print object id
        ## print(id(self))
        ## print(self.ArticleKey)
        ## ArticlePath="/home/samman/Documents/MobileApplications/Learn/LibraryKivy/Library/sequino2022omics.pdf"
        
        ## # if system is linux then open the pdf file
        ## if sys.platform == "linux":
        ##     os.system("xdg-open " + ArticlePath)
        ## else:
        ##     webbrowser.open(ArticlePath)
        # ArticleInfoDatabase=get_article_info_from_database(self.ArticleKey)
        # self.parent.parent.parent.parent.parent.ids.article_info.text=format_ArticleInfo(ArticleInfoDatabase)
        # open database
        global SciLibraDatabaseName
        global PreviousArticleClickedKey
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article info
        self.parent.parent.parent.parent.parent.ids.article_info.text=articledata.ArticleInfo2Restuct(libcon, self.ArticleKey)
        pass


class CategoryiesDropDown(DropDown):
    def createCategoryDropDown(menu_bar, clusteringCategory):
        global TreeCluster_Buttons
        # add article clusters
        cluster_buttons = []
        for cluster in clusteringCategories:
            btn = Button(text=cluster, size_hint_y=None, height=44, background_color = (1,1,1,1), color=(1,0,0,1))
            # if the group is selected then change the background color to red
            if cluster == clusteringCategory:
                btn.background_color = (1,0,0,1)
                btn.color = (1,1,1,1)
            cluster_buttons.append(btn)

        # add buttons to the tree_view_drop
        for cbtni in range(len(cluster_buttons)):
            # white color code (1,1,1,1)
            # gbtn.bind(on_release=lambda btn: self.menu_bar.select_article_group(gbtn.text , gbtn))
            cluster_buttons[cbtni].bind(on_release=lambda btn: menu_bar.select_article_cluster(btn.text))
            menu_bar.tree_view_drop.add_widget(cluster_buttons[cbtni])
        # assign the buttons to the global variable
        TreeCluster_Buttons = cluster_buttons
        return menu_bar    
    def changeSelectionColor(Category):
        # Change the color of the selected clustering category
        for cbtn in TreeCluster_Buttons:
            if cbtn.text != Category:
                cbtn.background_color = (1,1,1,1)
                cbtn.color = (1,0,0,1)
            else:
                cbtn.color = (1,1,1,1)
                cbtn.background_color = (1,0,0,1)    
class MainScreen(Screen):
    pass

class LibraryTreeview(TreeView):
    # create a new article tree view
    # inputs:
        # tree_view: TreeView object
        # libcon: Library connection
        # clusteringCategory: Clustering category
    # dependencies: librarydatabase, librarytreeview
    # outputs:
        # tree_view: TreeView object
    def createTreeView(tree_view, libcon, clusteringCategory):        
        # get the articles IDs for this category
        ArticlesCluster = librarydatabase.getAllArticleIDsfromSubTable(libcon, clusteringCategory)
        # # if the cluster is empty then return
        if len(ArticlesCluster) == 0:
            return tree_view # return the tree view without any changes
        # clear nodes from the tree view
        for node in [i for i in  tree_view.iterate_all_nodes()]:
             tree_view.remove_node(node)
        # add new nodes to the tree view
        for category in ArticlesCluster:
            narticles = len(ArticlesCluster[category])
            articlestitles = librarydatabase.getArticleValuesforKeySetInSubTable(libcon, 'title', ArticlesCluster[category]).values()
            # to list
            articlestitles = list(articlestitles)
            # if the clustering category is not title then add the cluster
            if clusteringCategory != "title":
                # add a node for the cluster with the cluster name and number of articles in the cluster
                cluster_node = tree_view.add_node(TreeViewLabel(text=str(category) + " (" + str(narticles) + ")", is_open=True))
                # add articles to the cluster node
                for an in range(narticles):
                    ArticleTitle = articlestitles[an]
                    ArticleKey = ArticlesCluster[category][an]
                    ArLabel=ArticleListLabel(text=ArticleTitle, ArticleKey=ArticleKey)
                    tree_view.add_node(ArLabel, cluster_node)
                # collapse the cluster node
                cluster_node.is_open = False
            else:
                ArticleKey = ArticlesCluster[category][0]
                ArLabel=ArticleListLabel(text=category, ArticleKey=ArticleKey)
                tree_view.add_node(ArLabel)
        # change the tree root text
        tree_view.root.text = "Articles clustered by " + clusteringCategory
        return tree_view

class SciLibraScreenManager(ScreenManager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        global SciLibraDatabaseName
        global articleInfoTable
        global dbSubTablesInfo
        # global TreeCluster_Buttons
        global TreeCluster_Buttons
        # Ids
        tree_view = self.ids.main_screen.ids.tree_view
        menu_bar = self.ids.main_screen.ids.menu_bar
        
        # # remove the database file if exists
        # if os.path.exists(SciLibraDatabaseName):
        #     os.remove(SciLibraDatabaseName)

        # initialize the database for the first time !!
        librarydatabase.initializeLibrary(SciLibraDatabaseName, articleInfoTable, dbSubTablesInfo)
        # Create a connection to the database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get Library properties
        libraryProperties = librarydatabase.getLibraryProperties(libcon)
        # get the clustering category        
        clusteringCategory = libraryProperties["clusteringcategory"]
        # get the articles IDs for this category
        tree_view = LibraryTreeview.createTreeView(tree_view, libcon, clusteringCategory)
        # close connection
        libcon.close()

        # create a drop down menu for the clustering categories
        menu_bar = CategoryiesDropDown.createCategoryDropDown(menu_bar, clusteringCategory)
        # change the selection color
        CategoryiesDropDown.changeSelectionColor(clusteringCategory)


    # open the article
    def open_article(self):
        tree_view = self.ids.main_screen.ids.tree_view
        if tree_view.selected_node is None:
            return
        # if it does not have ArticleKey then return
        if not hasattr(tree_view.selected_node, "ArticleKey"):
            return
        ArticleKey = tree_view.selected_node.ArticleKey
        if ArticleKey == "":
            return
        
        # open database
        global SciLibraDatabaseName
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article info from the main table
        ArticleInfoDatabase = librarydatabase.getArticleInfoByIDfromMainTable(libcon, ArticleKey)
        # close connection
        libcon.close()
        # get the article path
        ArticlePath = ArticleInfoDatabase["folderpath"] + "/" + ArticleKey + ".pdf"
        
        
        if sys.platform == "linux":
            os.system("xdg-open " + ArticlePath)
        else:
            webbrowser.open(ArticlePath)
        # open the article
        pass

class ArticleInfoBlockSingleLine(Widget):
    # to change the label text
    title_text = StringProperty('')
    def __init__(self, title_text=None, **kwargs):
        super().__init__(**kwargs)
        # print("#########")
        # print(self.title_text)
        
class ArticleInfoBlockMultiLine (Widget):
    pass
class EditScreen(Screen):
    def buttonPress(self):
        # change screen
        self.manager.current = "main"

class SciLibra(App):
    def build(self):
        # create a database
        # create_database()
        return SciLibraScreenManager()

if __name__ == '__main__':
    SciLibra().run()
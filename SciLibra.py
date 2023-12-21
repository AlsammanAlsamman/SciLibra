#!/usr/bin/python3


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
from time import sleep
from kivy.uix.checkbox import CheckBox
from kivy.clock import Clock
from kivy.config import Config

Config.set('kivy','window_icon','icon.png')


################# Local Imports #####################
import librarydatabase
import articledata
import re

################# Global Variables #####################
# Main Table
articleInfoTable = {'ID': 'text',
                'title': 'text',
                'author': 'text',
                'year': 'text',
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
                
                'publisher': 'text'}
# Sub Tables
dbSubTablesInfo = {
            'taggroups': 'text'
            , 'author': 'text'
            , 'title': 'text'
            , 'keywords': 'text'
            , 'year': 'text'
            ,'comment': 'text'
            , 'journal': 'text'
            , 'firstpageimages': 'blob'}

# Clustering Categories
clusteringCategories = ['title', 'author', 'year', 'journal', 'taggroups', 'keywords']



# Kivy TreeView Clusters
TreeCluster_Buttons = None
PreviousArticleClickedKey = None
currentClusterView = None
currentLibraryViewPressed = False
SelectedArticle = None
currentArticleEditInfo = None

SciLibraDatabaseName = "scilibraLibrary.db"

ExampleBibFile = "Articles_example.bib" #!!
DefultFolderPath = "/home/samman/Documents/MobileApplications/Learn/SciLibra" #!!

# Library parameters
Click2ReturnToolTip = True

# search criteria
searchCriteria = {}

# Current Library View Current Page
currentLibraryViewPage = 1
currentClusteringCategory="title"
orginalLibraryView = None # used to store the original library view

# Seacrhing
searchStatus = False

# Available Values
AvailableValues = {}
########## Classes ############
class MenuBar(BoxLayout):
    article_groups = ObjectProperty(None)
    # get the tree view from the main screen
    # Librar = property(lambda self: self.parent.parent.ids.tree_view)
    librarylistview = property(lambda self: self.parent.parent.ids.library_view.ids.list_tool)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)     

    def show_help(self):
        pass
    
    def show_about(self):
        about = AboutSciLibra()
        about.open()
    
        pass
    
    def add_article(self):
        pass
    
    def dismiss_popup(self):
        print("Hello")
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
        # LibraryTreeview.createTreeView(self.tree_view, libcon, Category)
        # createLibrayViewList(self,LibraryView, libcon, clusteringCategory):
        LibraryListView.createLibrayViewList(self.librarylistview, libcon, Category)
        # close connection
        libcon.close()
    def updatefolderpath(self):
        updateLoader = UpdateFolderPath()
        updateLoader.open()

    def filter_database(self):
        # open the filter database popup
        filterdatabase = FilterDatabase()
        filterdatabase.open()
    
    def save_database_as_bibtex(self):
        # get all articles from the database
        global SciLibraDatabaseName
        # open file chooser
        content = SaveDialog(cancel=self.dismiss_popup)
        content.save = self.saveDatabase2Bib
        self._popup = Popup(title="Save file", content=content,
                            size_hint=(0.9, 0.9), auto_dismiss=False)
        self._popup.open()

        
    def search_article(self):
        self.parent.parent.manager.current = "search"
        pass
    
    def saveDatabase2Bib(self, path, filename):
        global SciLibraDatabaseName
        
        # check validity of the file name
        if filename == "":
            popup = PopUpMessage(title="No File Name", message="Please enter a file name")
            # open the popup
            popup.open()
            return
        # check file name validity according to not containing any special characters
        if re.search('[<>?|*:"/]', filename) != None:
            popup = PopUpMessage(title="Invalid File Name", message="Please enter a valid file name")
            # open the popup
            popup.open()
            return

        # open the database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get all articles
        # articles = librarydatabase.getAllArticlesfromMainTable(libcon)
        # pdf path sub table
        pdfpathSubTable = librarydatabase.getAllArticlesfromSubTable(libcon, 'comment')
        print(pdfpathSubTable)
        # comment
        # abstrcat
        # # close connection
        # libcon.close()

        # dismiss the popup
        self.dismiss_popup()
        pass


class SaveDialog(FloatLayout):
    save = ObjectProperty(None)
    file_name = ObjectProperty(None)
    cancel = ObjectProperty(None)
    filechooser = ObjectProperty(None)
    

class SearchCriteria(BoxLayout):
    criteria = StringProperty('')
    value = "up"

    def check_criteria(self, value):
        global searchCriteria

        # change the value of the criteria
        if value == "down":
            self.value = "up"
            searchCriteria[self.criteria] = "down"
        else:
            self.value = "down"
            searchCriteria[self.criteria] = "up"

        # if the criteria is All/NotAll then change the status of all criteria
        # if "All/NotAll" is down then change all criteria to down
        if self.criteria == "All/NotAll" and self.value == "down":
            # clear the search criteria
            searchCriteria = {}
            for chbcr in self.parent.parent.parent.ids:
                # check if chbcr is a SearchCriteria object
                if isinstance(self.parent.parent.parent.ids[chbcr], SearchCriteria):
                    # if it is active then deactivate it
                    # if its not All
                    self.parent.parent.parent.ids[chbcr].ids.criteria_checkbox.active = True
                    self.parent.parent.parent.ids[chbcr].SelectedStatus = True
                    searchCriteria[self.parent.parent.parent.ids[chbcr].criteria] = "up"
                    
        # if "All/NotAll" is up then change all criteria to up
        if self.criteria == "All/NotAll" and self.value == "up":
            for chbcr in self.parent.parent.parent.ids:
                # check if chbcr is a SearchCriteria object
                if isinstance(self.parent.parent.parent.ids[chbcr], SearchCriteria):
                    # if it is active then deactivate it
                    # if its not All
                    self.parent.parent.parent.ids[chbcr].ids.criteria_checkbox.active = False
                    self.parent.parent.parent.ids[chbcr].SelectedStatus = False
                    # add the criteria to the search criteria
                    searchCriteria[self.parent.parent.parent.ids[chbcr].criteria] = "down"    

class PopUpMessage(Popup):
    message = StringProperty('')
    closeFunction = ObjectProperty(None)
    def __init__(self, message=None, closeFunction=None, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        if closeFunction != None:
            self.closeFunction = closeFunction
        # make the size of the popup depend on the size of the message
        # self.size_hint = (None, None)
        # self.size = ( 500,len(self.message)/20*2+200)
        
    def copy_message(self):
        # copy the message to clipboard
        Clipboard.copy(self.message)
        # close the popup
        self.dismiss()
    def close_popup(self):
        if self.closeFunction != None:
            self.closeFunction()
            self.dismiss()
        else:
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

    def edit_article(self):
        global SciLibraDatabaseName
        global SelectedArticle
        global currentArticleEditInfo
        # change screen
        if SelectedArticle == None:
            popup = PopUpMessage(title="No Article Selected", message="Please select an article first")
            # open the popup
            popup.open()
            return
        self.manager.current = "Edit"
        # open database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)

        ArticleDatabaseInfo = librarydatabase.getArticleInfoByIDfromMainTable(libcon, SelectedArticle)
        # get 

        # check if the article is not found
        if ArticleDatabaseInfo == None:
            popup = PopUpMessage(title="Article Not Found", message="Article is not found")
            # open the popup
            popup.open()
            return
        
        articletextinfo = []
        for info in ArticleDatabaseInfo:
            # if the info is not empty then add it to the info box
            if ArticleDatabaseInfo[info] != None:
                # articletextinfo += "\n>>"+info + "<<\n" + str(ArticleDatabaseInfo[info]) + "\n"
                articletextinfo.append(">>"+info + "<<")
                articletextinfo.append(str(ArticleDatabaseInfo[info]))
        # add comments
        articletextinfo.append(">>comment<<")
        comment = librarydatabase.getArticleInfoByIDfromSubTable(libcon, 'comment',SelectedArticle)
        if comment != None:
            articletextinfo.append(comment)        
        # close connection
        libcon.close()

        # change the text of the article info box
        self.parent.ids.Edit_screen.ids.article_info.text = "\n".join(articletextinfo)
        # change the currentArticleEditInfo
        currentArticleEditInfo = ArticleDatabaseInfo
        pass
    
    def delete_article(self):
        global SciLibraDatabaseName
        global SelectedArticle
        global dbSubTablesInfo
        global currentLibraryView

        
        # change screen
        if SelectedArticle == None:
            popup = PopUpMessage(title="No Article Selected", message="Please select an article first")
            # open the popup
            popup.open()
            return
        # open database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # delete the article from the main table
        deleteted = librarydatabase.deleteArticle(libcon, SelectedArticle, dbSubTablesInfo)
        # close connection
        libcon.close()
        # create a popup message
        if deleteted:
            popup = PopUpMessage(title="Article Deleted", message="Article is deleted successfully")
            # open the popup
            popup.open()
        else:
            popup = PopUpMessage(title="Article Not Deleted", message="Article is not deleted")
            # open the popup
            popup.open()
        pass
    def manage_comments(self):
        global SciLibraDatabaseName
        global SelectedArticle
        # change screen
        if SelectedArticle == None:
            popup = PopUpMessage(title="No Article Selected", message="Please select an article first")
            # open the popup
            popup.open()
            return
        # show the comments manager
        commentmanager = CommentsManager()
        
        commentmanager.ids.comments_grid.add_widget(Comment(text="Hello", author="Samman"))
        # #self.parent.ids.comments_manager.add_widget(commentmanager)
        # # # open edit info screen
        self.manager.current = "Comments"
        pass
        
    def manage_info(self,target):
        # change the color of the target
        # current selected article
        global SelectedArticle
        global SciLibraDatabaseName

        # if no article is selected then return
        if SelectedArticle == None:
            popup = PopUpMessage(title="No Article Selected", message="Please select an article first")
            # open the popup
            popup.open()
            return
        # open database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article info from the sub table
        ArticleInfo = librarydatabase.getArticleInfoByIDfromSubTable2(libcon, target, SelectedArticle)
        allvalues = librarydatabase.getArticleInfoValuesfromSubTable(libcon, target)
        
        # close connection
        libcon.close()
        
        # open Edit info screen
        targetsList = ArticleInfo
        randomsources = allvalues
        # if no values in the target then show an empty list
        if targetsList is None:
            targetsList = []
        myDualListBox = DualListBox(TargetLabel=target, SourceLabel="Manage " + target, TargetList=targetsList, SourceList=randomsources, articleID=SelectedArticle)
        # clear the dual list box
        self.parent.ids.EditInfo_screen.ids.dual_list.clear_widgets()
        self.parent.ids.EditInfo_screen.ids.dual_list.add_widget(myDualListBox)
        self.manager.current = "EditInfo"
        pass
class CommentsManager(Screen):
    # add one comment to test
    comments_grid = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # add one button to test
        # print(self.ids)
        pass
        # self.ids.comments_grid.add_widget(Comment())


class Comment(BoxLayout):
    text = StringProperty('')
    author = StringProperty('')
class EditInfoScreen(Screen):
    pass
class BoxItem(BoxLayout):
    ItemLabel = StringProperty()
    ItemSource = ObjectProperty()
    pressed = False
    def on_press(self):
        if not self.pressed:
            self.pressed = True
            # change color to blue
            self.ids.ItemButton.background_color = (0, 0, 1, 1)
        else:
            self.pressed = False
            # change color
            self.ids.ItemButton.background_color = (0.753, 0.753, 0.753, 1)

class DualListBox(Widget):
    # List of the items in the SourceBox for backup  
    TargetLabel = StringProperty()
    SourceLabel = StringProperty()
    articleID = StringProperty()
    SourceList = []
    # save function to ovveride
    def update(self):
        # update the database for this article
        global SciLibraDatabaseName
        # new values for the target
        newValues = []
        # get all children of the TargetBox
        for child in self.ids.TargetBox.children:
            newValues.append(child.ItemLabel)

        # open database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article info from the sub table
        ArticleInfo = librarydatabase.getArticleInfoByIDfromSubTable2(libcon, self.TargetLabel, self.articleID)
        # compare the new values with the old values and select new values and deleted values
        if ArticleInfo == None:
            ArticleInfo = []
        values2add = [value for value in newValues if value not in ArticleInfo]
        values2delete = [value for value in ArticleInfo if value not in newValues]
        # update the database
        librarydatabase.updateArticleInfoInSubTable(libcon, self.TargetLabel, self.articleID, values2add, values2delete)
        # # close connection
        libcon.close()
        # create a popup message
        popup = PopUpMessage(title="Article Info Updated", message="Article info is updated successfully")
        # open the popup
        popup.open()
        pass


    def __init__(self, TargetLabel=None, SourceLabel=None, TargetList=None, SourceList=None, **kwargs):
        super().__init__(**kwargs)
        # if the user did not set the TargetLabel
        if TargetLabel != None:
            self.TargetLabel = TargetLabel
        if SourceLabel != None:
            self.SourceLabel = SourceLabel

        for target in TargetList:
            self.ids.TargetBox.add_widget(BoxItem(ItemLabel=target,  
                                                  size_hint_y=None, height=40, ItemSource=self.ids.TargetBox))

        for source in SourceList:
            self.ids.SourceBox.add_widget(BoxItem(ItemLabel=source,  
                                                  size_hint_y=None, height=40, ItemSource=self.ids.SourceBox))
        #         # add 100 buttons to the TargetBox
        # # for i in range(100):
        # #     self.ids.TargetBox.add_widget(BoxItem(ItemLabel=str(i),  size_hint_y=None, height=40, ItemSource=self.ids.TargetBox))
        # #add '99' buttons to the TargetBox
        # self.ids.TargetBox.add_widget(BoxItem(ItemLabel=str('1'),  size_hint_y=None, height=40, ItemSource=self.ids.TargetBox))

        # # add 100 buttons to the SourceBox
        # for i in range(100):
        #     self.ids.SourceBox.add_widget(BoxItem(ItemLabel=str(i),  size_hint_y=None, height=40, ItemSource=self.ids.SourceBox))
    def MoveItemToTarget(self, SourceBox, TargetBox):
        chicked = {}
        TargetItems = []
        # get all children of the TargetBox
        for child in TargetBox.children:
            TargetItems.append(child.ItemLabel)
        # get all children of the SourceBox
        for child in SourceBox.children:
            # check if the child is pressed
            # if SourceList is empty add all children to the SourceList
            if child.pressed:
                ## add the child to the chicked
                chicked[child.ItemLabel] = child
        # move the chicked to the TargetBox
        for child in chicked.values():
            # # remove the child from the SourceBox
            SourceBox.remove_widget(child)
            # if the item is already exist in the TargetBox
            if child.ItemLabel in TargetItems:
                return
            # # add the child to the TargetBox
            TargetBox.add_widget(child)
            # # change the color of the button
            child.ids.ItemButton.background_color = (0.753, 0.753, 0.753, 1)
            # # change the pressed state
            child.pressed = False
        # remove from the SourceList if it is exist
        for child in chicked.values():
            if child in self.SourceList:
                self.SourceList.remove(child)

    def MoveItemToSource(self, SourceBox, TargetBox):
        chicked = {}
        sourceItems = []
        # get all children of the SourceBox
        for child in SourceBox.children:
            sourceItems.append(child.ItemLabel)

        # get all children of the TargetBox
        for child in TargetBox.children:
            # check if the child is pressed
            if child.pressed:
                ## add the child to the chicked
                chicked[child.ItemLabel] = child
                
        # move the chicked to the SourceBox
        for child in chicked.values():
            # # remove the child from the TargetBox
            TargetBox.remove_widget(child)
            # if the item is already exist in the SourceBox
            if child.ItemLabel in sourceItems:
                return
            # # add the child to the SourceBox
            SourceBox.add_widget(child)
            # # change the color of the button
            child.ids.ItemButton.background_color = (0.753, 0.753, 0.753, 1)
            # # change the pressed state
            child.pressed = False

    def search(self, pattern, SourceBox):
        matched = {}
        # get all children of the SourceBox
        for child in SourceBox.children:
            # save the child in the SourceList
            self.SourceList.append(child)
            # check if the child label match the pattern
            if re.search(pattern, child.ItemLabel):
                ## add the child to the matched
                matched[child.ItemLabel] = child
        # remove all children from the SourceBox
        SourceBox.clear_widgets()
        # add the matched to the SourceBox
        for child in matched.values():
            SourceBox.add_widget(child)

    def UndoSearch(self, SourceBox):
        # if the SourceList is empty
        if len(self.SourceList) == 0:
            return
        # remove all children from the SourceBox
        SourceBox.clear_widgets()
        # add the SourceList to the SourceBox
        for child in self.SourceList:
            SourceBox.add_widget(child)
        # clear the SourceList
        self.SourceList = []

    def AddItemToTarget(self, TargetBox, TargetAdd):
        # if it is not empty
        newItem=""
        newItemText = TargetAdd.text
        if newItemText == '':
            popup = Popup(title='Error', content=Label(text='Please enter a value'), size_hint=(None, None), size=(200, 200), auto_dismiss=True)
            popup.open()
            return
        else:
            # check if the item is already exist
            for child in TargetBox.children:
                if child.ItemLabel == newItemText:
                    popup = Popup(title='Error', content=Label(text='The item is already exist'), size_hint=(None, None), size=(200, 200), auto_dismiss=True)
                    popup.open()
                    return
            # create a new item
            newItem = BoxItem(ItemLabel=newItemText, size_hint_y=None, height=40, ItemSource=TargetBox)
            # add the new item to the SourceBox
            TargetBox.add_widget(newItem)
            # clear the text input
            TargetAdd.text = ''
    def Close(self):
        # change SciLibraScreenManager to MainScreen
        self.parent.parent.parent.current = "main"
        pass
class SearchScreen(Screen):
    def gotoMainScreen(self):
        self.manager.current = "main"
        pass
    def createLibraryViewForSearch(self, libcon, ArticlesIDHit):
        global currentLibraryView
        
        ArticleTitles = librarydatabase.getArticleValuesforKeySetInSubTable(libcon, 'title', ArticlesIDHit)
        # create Cluster
        ArticlesCluster = {}
        for article in ArticleTitles:
            # get the cluster name
            clustername = ArticleTitles[article]
            # if the cluster is not in the cluster then add it
            if clustername not in ArticlesCluster:
                ArticlesCluster[clustername] = []
            # add the article to the cluster
            ArticlesCluster[clustername].append(article)

        # create ArticlesClusterList
        ArticlesClusterList = []
        for category in ArticlesCluster:
            narticles = len(ArticlesCluster[category])
            # create a dictionary for the cluster
            cluster = {}
            cluster["name"] = category
            cluster["narticles"] = narticles
            # add the cluster to the list
            ArticlesClusterList.append(cluster)
        
        # change the currentLibraryView
        currentLibraryView = ArticlesCluster
        LibraryListView.createLibrayViewListForList(self.parent.ids.main_screen.ids.library_view.ids.list_tool, ArticlesClusterList)
        pass

    def search_article(self):
        global searchCriteria
        global SciLibraDatabaseName
        global currentLibraryView
        
        searchText = self.ids.search_criteria_text.text.strip()
        
        if searchText == "Please enter search criteria" or searchText == "":
            popup = PopUpMessage(title="No Search Text", message="Please enter a search text")
            # open the popup
            popup.open()
            return
        
        # if it contains ||| then split it
        if "|||" in searchText:
            searchText = searchText.split("|||")
        else:
            searchText = [searchText]
        
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        
        ArticlesIDHit = []
        searchReport = {}
        for searchQuery in searchText:
            if searchQuery not in searchReport:
                searchReport[searchQuery] = {}
                searchReport[searchQuery]["Hits"] = 0
                searchReport[searchQuery]["Criteria"] = {}

            for criteria in searchCriteria:
                if searchCriteria[criteria] == "up" and criteria != "All/NotAll":
                    # is this criteria from Main Table
                    if criteria in articleInfoTable:
                        crHits=librarydatabase.searchArticleInfoFromLibraryMainTable(libcon, searchQuery, criteria)
                        if len(crHits) == 0:
                            continue
                        ArticlesIDHit+=crHits
                        searchReport[searchQuery]["Hits"]+=len(crHits)
                        if criteria not in searchReport[searchQuery]["Criteria"]:
                            searchReport[searchQuery]["Criteria"][criteria] = 0
                        searchReport[searchQuery]["Criteria"][criteria] += len(crHits)
                    else:
                        # is this criteria from Sub Table
                        crHits=librarydatabase.searchArticleInfoFromLibrarySubTable(libcon, searchQuery, criteria)
                        if len(crHits) == 0:
                            continue
                        ArticlesIDHit+=crHits
                        searchReport[searchQuery]["Hits"]+=len(crHits)
                        if criteria not in searchReport[searchQuery]["Criteria"]:
                            searchReport[searchQuery]["Criteria"][criteria] = 0
                        searchReport[searchQuery]["Criteria"][criteria] += len(crHits)
                        
        # if empty then return
        if len(ArticlesIDHit) == 0:
            popup = PopUpMessage(title="No Articles Found", message="No articles found")
            # open the popup
            popup.open()
            return
        
        # remove duplicates
        ArticlesIDHit = list(set(ArticlesIDHit))
        # # create the library view
        self.createLibraryViewForSearch(libcon, ArticlesIDHit)
        # # close connection
        libcon.close()

        # create a popup message on close go to the main screen
        popup = PopUpMessage(title="Search Report", message=self.searchReport(searchReport), closeFunction=self.gotoMainScreen)
    
        # open the popup
        popup.open()
        
    def searchReport(self,searchReport):
        report = ""
        for searchQuery in searchReport:
            report += "-"*10 + "\n"
            report += "Search Query: " + searchQuery + "\n"
            report += "Hits: " + str(searchReport[searchQuery]["Hits"]) + "\n"
            report += "Criteria: " + "\n"
            for criteria in searchReport[searchQuery]["Criteria"]:
                report += "\t" + criteria + ": " + str(searchReport[searchQuery]["Criteria"][criteria]) + "\n"
        return report



# Contains ArticleGroup
class LibraryListView(Widget):
    

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def getArticleCluster(libcon, clusteringCategory):
        global SciLibraDatabaseName
        global currentLibraryView
        # get the articles IDs for this category
        ArticlesCluster = librarydatabase.getAllArticleIDsfromSubTable(libcon, clusteringCategory)
        
        # if empty then return
        if len(ArticlesCluster) == 0:
            return ArticlesCluster
        # create a list of dictionaries for the Articles Clusters
        ArticlesClusterList = []
        for category in ArticlesCluster:
            narticles = len(ArticlesCluster[category])
            # create a dictionary for the cluster
            cluster = {}
            cluster["name"] = category
            cluster["narticles"] = narticles
            # add the cluster to the list
            ArticlesClusterList.append(cluster)
        # sort the list by the number of articles
        ArticlesClusterList.sort(key=lambda x: x["narticles"], reverse=True)
        # change the currentLibraryView
        currentLibraryView = ArticlesCluster
        return ArticlesClusterList
    
    def createLibrayViewList(LibraryView, libcon, clusteringCategory):
        global currentLibraryView
        global currentLibraryViewPage
        global currentClusteringCategory
        # reset the currentLibraryViewPage
        currentLibraryViewPage = 1
        # get the articles IDs for this category
        ArticlesCluster = LibraryListView.getArticleCluster(libcon, clusteringCategory)
        # if the cluster is empty then return
        if len(ArticlesCluster) == 0:
            return LibraryView # return the tree view without any changes
        # change the currentLibraryView
        currentLibraryView = ArticlesCluster
        currentClusteringCategory = clusteringCategory

        # take only the first 50 clusters
        ArticlesCluster = ArticlesCluster[(currentLibraryViewPage-1)*100:currentLibraryViewPage*100]
        
        # if LibraryView is not empty then clear it
        if len(LibraryView.children) > 0:
            for node in [i for i in  LibraryView.children]:
                    LibraryView.remove_widget(node)
        # add new nodes to the tree view
        for cluster in ArticlesCluster:
            category_name = cluster["name"]
            category_narticles = cluster["narticles"]
            # Add ArticleGroup
            clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                        # parble
                                        background_color = [0, 0.5, 0, 1])
            clusterGroup.clusteringcategory = clusteringCategory
            clusterGroup.articlegroupname = category_name
            clusterGroup.parentgroup = LibraryView
            LibraryView.add_widget(clusterGroup)
        # clear the search status
        global searchStatus 
        searchStatus = False


    def createLibrayViewListForList(LibraryView, ArticlesCluster):
        global currentLibraryView
        # if the cluster is empty then return
        if len(ArticlesCluster) == 0:
            return LibraryView
        # change the currentLibraryView
        currentLibraryView = ArticlesCluster
        # if LibraryView is not empty then clear it
        if len(LibraryView.children) > 0:
            for node in [i for i in  LibraryView.children]:
                    LibraryView.remove_widget(node)
        # add new nodes to the tree view
        for cluster in ArticlesCluster:
            category_name = cluster["name"]
            category_narticles = cluster["narticles"]
            # Add ArticleGroup
            clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                        # parble
                                        background_color = [0, 0.5, 0, 1])
            clusterGroup.clusteringcategory = 'title'
            clusterGroup.articlegroupname = category_name
            clusterGroup.parentgroup = LibraryView
            LibraryView.add_widget(clusterGroup)
        # clear the search status
        global searchStatus
        searchStatus = False
        
    def nextPage(self):
        global currentLibraryViewPage
        global currentLibraryView
        global currentClusteringCategory
        currentView=self.ids.list_tool

        # if currentLibraryView is empty then return
        if currentView == None:
            return
        
        # add one to the currentLibraryViewPage
        if currentLibraryViewPage*100 >= len(currentLibraryView):
            popup = PopUpMessage(title="No More Articles", message="No more articles")
            # open the popup
            popup.open()
            return
        currentLibraryViewPage += 1

        # clear the currentLibraryView
        if len(currentView.children) > 0:
            for node in [i for i in  currentView.children]:
                    currentView.remove_widget(node)
      
        #next set of clusters
        ArticlesCluster = currentLibraryView[(currentLibraryViewPage-1)*100:currentLibraryViewPage*100]
        # add new nodes to the tree view
        for cluster in ArticlesCluster:
            category_name = cluster["name"]
            category_narticles = cluster["narticles"]
            # Add ArticleGroup
            clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                        # parble
                                        background_color = [0, 0.5, 0, 1])
            clusterGroup.clusteringcategory = currentClusteringCategory
            clusterGroup.articlegroupname = category_name
            clusterGroup.parentgroup = currentView
            currentView.add_widget(clusterGroup)
        pass
    
    def previousPage(self):
        global currentLibraryViewPage
        global currentLibraryView
        global currentClusteringCategory

        currentView = self.ids.list_tool

        # if currentLibraryView is empty then return
        if currentView == None:
            return
        
        # remove one from the currentLibraryViewPage
        if currentLibraryViewPage == 1:
            popup = PopUpMessage(title="No More Articles", message="No more articles")
            # open the popup
            popup.open()
            return
        
        currentLibraryViewPage -= 1

        # clear the currentLibraryView
        if len(currentView.children) > 0:
            for node in [i for i in  currentView.children]:
                    currentView.remove_widget(node)
      
        #next set of clusters
        ArticlesCluster = currentLibraryView[(currentLibraryViewPage-1)*100:currentLibraryViewPage*100]
        # add new nodes to the tree view
        for cluster in ArticlesCluster:
            category_name = cluster["name"]
            category_narticles = cluster["narticles"]
            # Add ArticleGroup
            clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                        # parble
                                        background_color = [0, 0.5, 0, 1])
            clusterGroup.clusteringcategory = currentClusteringCategory
            clusterGroup.articlegroupname = category_name
            clusterGroup.parentgroup = currentView
            currentView.add_widget(clusterGroup)
        pass

    def search(self, text):
        global searchStatus
        if searchStatus == True:
            # sorry you can't search while searching
            popup = PopUpMessage(title="Search in Progress", message="Sorry you can't search on a search result press X to clear the search")
            # open the popup
            popup.open()
            return
        global orginalLibraryView
        # search for the text in the library
        global currentLibraryView
        # print all the text of the library
        newLibraryView = []
        for cluster in currentLibraryView:
            # check if the text/pattern is in the cluster name
            clustername = cluster["name"]
            if re.search(text, clustername, re.IGNORECASE) != None:
                newLibraryView.append(cluster)
        # save the orginalLibraryView to be used later
        orginalLibraryView = currentLibraryView
        # change the currentLibraryView
        currentLibraryView = newLibraryView
        # change the library view
        # clear the currentLibraryView
        currentView = self.ids.list_tool
        # if the library view original is empty then save the original library view
       
        if len(currentView.children) > 0:
            for node in [i for i in  currentView.children]:
                    currentView.remove_widget(node)
        # add new nodes to the tree view
        for cluster in newLibraryView:
            category_name = cluster["name"]
            category_narticles = cluster["narticles"]
            # Add ArticleGroup
            clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                        # parble
                                        background_color = [0, 0.5, 0, 1])
            clusterGroup.clusteringcategory = currentClusteringCategory
            clusterGroup.articlegroupname = category_name
            clusterGroup.parentgroup = currentView
            currentView.add_widget(clusterGroup)
        # change the search status
        searchStatus = True
        pass

    def clearSearch(self):
        global currentLibraryView
        global orginalLibraryView

        # check that the orginalLibraryView is not empty
        if orginalLibraryView == None:
            return
        # clear the currentLibraryView
        currentView = self.ids.list_tool
        if len(currentView.children) > 0:
            for node in [i for i in  currentView.children]:
                    currentView.remove_widget(node)
        # add new nodes to the tree view
        for cluster in orginalLibraryView:
            category_name = cluster["name"]
            category_narticles = cluster["narticles"]
            # Add ArticleGroup
            clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                        # parble
                                        background_color = [0, 0.5, 0, 1])
            clusterGroup.clusteringcategory = currentClusteringCategory
            clusterGroup.articlegroupname = category_name
            clusterGroup.parentgroup = currentView
            currentView.add_widget(clusterGroup)
        # change the currentLibraryView
        currentLibraryView = orginalLibraryView
        # clear the orginalLibraryView
        orginalLibraryView = None
        # change the search status
        global searchStatus
        searchStatus = False
        pass
class ArticleGroup(Button):
    clusteringcategory = StringProperty('')
    articlegroupname = StringProperty('')
    parentgroup = ObjectProperty(None)
    articleKeys = []
    articleTitles = []
    def __init__(self, **kwargs):
        super(ArticleGroup, self).__init__(**kwargs)
        
        self.height = 40
        self.size_hint_y = None
        # width is the same as the parent
        self.size_hint_x = 1
        # if text is too long then split it on multiple lines
        if len(self.text) > 50:
            newtext = ""
            for i in range(0, len(self.text), 50):
                newtext += self.text[i:i+50] + "\n"
            self.text = newtext
            # add more height according to the number of lines
            self.height += 20 * (len(self.text) // 50)

    def createArticleGroupView(groupname, libraryView, libcon, clusteringCategory):
        global SciLibraDatabaseName
        
        # get the articles IDs for this category
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        ArticlesCluster = librarydatabase.getAllArticleIDsfromSubTable(libcon, clusteringCategory)
        # get the articles titles
        titleDBresults = librarydatabase.getArticleValuesforKeySetInSubTable(libcon, 'title', ArticlesCluster[groupname])
        articleKeys = list(titleDBresults.keys())
        articlestitles = list(titleDBresults.values())
        # close connection
        libcon.close()

        if len(articleKeys) == 0:
            return

        # Create an ArticleGroup button for this group (a title button)
        articleGroup = ArticleGroup(text=groupname, background_color = 
                                    # gray color code (0.5, 0.5, 0.5, 1)
                                    [0.5, 0.5, 0.5, 1],
                                    # black border
                                    border = [0, 0, 0, 0.5]) 
                                    
        articleGroup.clusteringcategory = clusteringCategory
        articleGroup.articlegroupname = groupname
        articleGroup.parentgroup = libraryView
        
        # clear all MyGroup widget from the LibraryView GridLayout
        if len(libraryView.children) > 0:
            for node in [i for i in  libraryView.children]:
                libraryView.remove_widget(node)
        # add to LibraryView
        libraryView.add_widget(articleGroup)
        
        # create a GroupMember button for each article
        for article in articlestitles:
            articleMember = GroupMember(text=article)
            articleMember.articleKey = articleKeys[articlestitles.index(article)]
            # add to LibraryView
            libraryView.add_widget(articleMember)

    def on_press(self):
        global currentLibraryViewPressed
        global currentLibraryView
        global currentLibraryViewPage
        global SelectedArticle
        # if the it was pressed before then return the LibraryView to the original state
        if not currentLibraryViewPressed:
            ArticleGroup.createArticleGroupView(self.articlegroupname, self.parentgroup, None, self.clusteringcategory)
            currentLibraryViewPressed = True
            # clear the selected article
            SelectedArticle = None
        else:
            # return the LibraryView to the original state
            # Clear all widgets from the LibraryView GridLayout
            for node in [i for i in  self.parentgroup.children]:
                self.parentgroup.remove_widget(node)
            # add the currentLibraryView to the LibraryView
            # according to the currentLibraryViewPage
            cluster = currentLibraryView[(currentLibraryViewPage-1)*100:currentLibraryViewPage*100]
            for category in cluster:
                category_name = category["name"]
                category_narticles = category["narticles"]
                # Add ArticleGroup
                clusterGroup = ArticleGroup(text=str(category_name) + " (" + str(category_narticles) + ")",
                                            # parble
                                            background_color = [0, 0.5, 0, 1])
                clusterGroup.clusteringcategory = self.clusteringcategory
                clusterGroup.articlegroupname = category_name
                clusterGroup.parentgroup = self.parentgroup
                self.parentgroup.add_widget(clusterGroup)
            currentLibraryViewPressed = False
        # create a tooltip for the button appears for 1 second
        if Click2ReturnToolTip:
            LibraryTooltip().createTooltip("To return to the previous view click again")
        pass

    

# class YesNoDialog(Popup):
#     message = StringProperty('')
#     yesFunction = ObjectProperty(None)
#     noFunction = ObjectProperty(None)
#     def __init__(self, message=None, yesFunction=None, noFunction=None, **kwargs):
#         super().__init__(**kwargs)
#         self.message = message
#         if yesFunction != None:
#             self.yesFunction = yesFunction
#         if noFunction != None:
#             self.noFunction = noFunction
#     def yes(self):
#         if self.yesFunction != None:
#             self.yesFunction()
#             self.dismiss()
#         else:
#             self.dismiss()
#     def no(self):
#         if self.noFunction != None:
#             self.noFunction()
#             self.dismiss()
#         else:
#             self.dismiss()


class LibraryTooltip(Popup):
    tooltip_text = StringProperty('') 
    def createTooltip(self, tooltip_text):
        # size
        self.tooltip_text = tooltip_text
        self.size=400, 200
        self.open()
        Clock.schedule_once(self.dismiss_popup, 2)

    def dismiss_popup(self, dt):
        self.dismiss()
    
    def do_not_show_again(self):
        global Click2ReturnToolTip
        Click2ReturnToolTip = False
        self.dismiss()

class GroupMember(Button):

    articleKey = StringProperty('')
    def __init__(self, **kwargs):
        super(GroupMember, self).__init__(**kwargs)
        self.background_color = [1, 0, 1, 1]
        self.height = 40
        self.size_hint_y = None
        # width is the same as the parent
        self.size_hint_x = 1
        # if text is too long then split it on multiple lines
        if len(self.text) > 50:
            newtext = ""
            for i in range(0, len(self.text), 50):
                newtext += self.text[i:i+50] + "\n"
            self.text = newtext
            # add more height according to the number of lines
            self.height += 20 * (len(self.text) // 50)

    def on_press(self):
        print(self.articleKey)
        global SciLibraDatabaseName
        global PreviousArticleClickedKey
        global SelectedArticle
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article info
        # self.parent.parent.parent.parent.parent.ids.article_info.text=articledata.ArticleInfo2Restuct(libcon, self.articleKey)
        # self.ids.main_screen.ids.article_info.text=articledata.ArticleInfo2Restuct(libcon, self.articleKey)
        ArticleText=articledata.ArticleInfo2Restuct(libcon, self.articleKey)
        # close connection
        libcon.close()
        if ArticleText == None:
            popup = PopUpMessage(title="Article Not Found", message="Article is not found")
            # open the popup
            popup.open()
            return
        self.parent.parent.parent.parent.parent.parent.parent.parent.ids.article_info.text=ArticleText
        SelectedArticle = self.articleKey

class SciLibraScreenManager(ScreenManager):

    objectinprogress = None
    processisrunning = False
    
    def progress_bar(self):
        popup = Popup(title='Progress Bar', content=Label(text='Hello world'), size_hint=(None, None), size=(400, 400))
        popup.open()
        while self.processisrunning:
            pass
        popup.dismiss()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        global SciLibraDatabaseName
        global articleInfoTable
        global dbSubTablesInfo
        # global TreeCluster_Buttons
        global TreeCluster_Buttons
        # Library Tree View
        librarylistview = self.ids.main_screen.ids.library_view.ids.list_tool

        # add buttons to the LibraryView
        
        menu_bar = self.ids.main_screen.ids.menu_bar
        # # initialize the database for the first time !!
        librarydatabase.initializeLibrary(SciLibraDatabaseName, articleInfoTable, dbSubTablesInfo)
        # # Create a connection to the database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # # get Library properties
        libraryProperties = librarydatabase.getLibraryProperties(libcon)
        # # get the clustering category        
        clusteringCategory = libraryProperties["clusteringcategory"]
        # # get the articles IDs for this category
        librarylistview = LibraryListView.createLibrayViewList(librarylistview, libcon, clusteringCategory)
        # # tree_view = LibraryTreeview.createTreeView(tree_view, libcon, clusteringCategory)
        # # close connection
        libcon.close()
        # create a drop down menu for the clustering categories
        menu_bar = CategoryiesDropDown.createCategoryDropDown(menu_bar, clusteringCategory)
        # change the selection color
        CategoryiesDropDown.changeSelectionColor(clusteringCategory)

    # open the article
    def open_article(self):
        global SciLibraDatabaseName
        global SelectedArticle
        if SelectedArticle == None:
            return
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        # get the article info from the main table
        ArticleInfoDatabase = librarydatabase.getArticleInfoByIDfromMainTable(libcon, SelectedArticle)
        # close connection
        libcon.close()
        # get the article path
        ArticlePath = ArticleInfoDatabase["folderpath"] + "/" + ArticleInfoDatabase["ID"] + ".pdf"
        
        if sys.platform == "linux":
            os.system("xdg-open " + ArticlePath)
        else:
            webbrowser.open(ArticlePath)
        # open the article
        pass

class FilterDatabase(Popup):
    def filterDatabase(self):
        global SciLibraDatabaseName
        global dbSubTablesInfo
        # open database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        
        # get the articles IDs for this category
        ArticlesCluster = librarydatabase.getReplicatesByColumn(libcon, 'title')
        
        # if empty then return
        if len(ArticlesCluster) == 0:
            popup = PopUpMessage(title="No Replicates", message="No replicates found")
            # open the popup
            popup.open()
            return
        
        # remove from main table
        librarydatabase.removeArticleKeysfromMainTable(libcon, ArticlesCluster)
        # remove from sub tables
        for tableName in dbSubTablesInfo:
            librarydatabase.removeArticleKeysfromSubTable(libcon, ArticlesCluster, tableName)
        # close connection
        libcon.close()

        # create a popup message
        popup = PopUpMessage(title="Removed Articles", message="\n".join(ArticlesCluster))
        # open the popup
        popup.open()

class AboutSciLibra(Popup):
    about_text = StringProperty('')
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.about_text = """SciLibra is a free and open source software for managing scientific articles.
Created by: Alsamman M. Alsamman
Emails: smahmoud [at] ageri.sci.eg
A.Alsamman [at] cgiar.org
SammanMohammed [at] gmail.com                        
License: MIT License - https://opensource.org/licenses/MIT
Disclaimer: The script comes with no warranty, use at your own risk
This script is not intended for commercial use"""

    def copy_message(self):
        Clipboard.copy(self.about_text)
        self.dismiss()

class EditScreen(Screen):
    article_info = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # print(self.ids)
    def get_article_info_updatefromText(self, text):
        newArticleInfo = {}
        # split the text into lines
        lines = text.split("\n")
        currentinfo = ""
        for line in lines:
            if ">>" in line:
                currentinfo = line[2:-2]
            else:
                if currentinfo not in newArticleInfo:
                    newArticleInfo[currentinfo] = ""
                newArticleInfo[currentinfo] += line.strip()
        return newArticleInfo
        
    def buttonPress(self):
        # change screen
        self.manager.current = "main"
        # add article ti
        print(self.article_info.text)
        # print(MainScreen().get_article_info_updatefromText("\n".join(articletextinfo)))
    def update_article(self):
        global SciLibraDatabaseName
        global SelectedArticle
        global currentArticleEditInfo
        # get the new article info
        newArticleInfo = self.get_article_info_updatefromText(self.article_info.text)
        # changes info
        changedInfo = []
        for info in newArticleInfo:
            # if not in currentArticleEditInfo then add it
            if info not in currentArticleEditInfo:
                currentArticleEditInfo[info] = ""
            # is there any change
            if newArticleInfo[info] != currentArticleEditInfo[info]:
                changedInfo.append(info)
        
        # if no change then return
        if len(changedInfo) == 0:
            popup = PopUpMessage(title="No Change", message="No change is made to the article")
            # open the popup
            popup.open()
            self.manager.current = "main"
            return
        
        # open database
        libcon = librarydatabase.create_connection(SciLibraDatabaseName)
        #update the main table
        for info in changedInfo:
            # if the info is in the main table then update it
            if info in articleInfoTable:
                librarydatabase.updateMainTableRow(libcon, info, SelectedArticle, newArticleInfo[info], forceUpdate=True)

        # update the sub tables
        for tableName in dbSubTablesInfo:
            if tableName in changedInfo:
                #updateSubTableRow(libcon, tableName, articleID, articleData, forceUpdate=False):
                librarydatabase.updateSubTableRow(libcon, tableName, SelectedArticle, newArticleInfo[tableName], forceUpdate=True)
        # close connection
        libcon.close()
        # create a popup message
        popup = PopUpMessage(title="Article Updated", message="Article is updated successfully")
        # open the popup
        popup.open()
        # change screen
        self.manager.current = "main"


class AvailableValue(Button):
    value = StringProperty('')
    pressed=False
    myParent = ObjectProperty(None)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = (1,1,1,1)
        self.size_hint_y = None
        self.height = 40
    def on_press(self):
        global AvailableValues
        if self.pressed:
            self.background_color = (1,1,1,1)
            self.pressed=False
            # add to parent
            
        else:
            self.background_color = (0,0,1,1)
            self.pressed=True
            AvailableValues[self.value] = 1

class SciLibra(App):
    def build(self):
        # create a database
        # create_database()
        self.icon = 'SciLibra.png'
        # change program icon 
        # change startup icon
        # self.on_icon='SciLibra_icon.png'
        # change icon
        return SciLibraScreenManager()

if __name__ == '__main__':
    SciLibra().run()